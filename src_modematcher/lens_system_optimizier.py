import numpy as np
from deap import base, creator, tools, algorithms
from scipy.optimize import minimize
from src_physics.beam import Beam
import random
import json
import config
from PyQt5.QtWidgets import QMessageBox, QProgressDialog, QApplication, QTableWidgetItem, QCheckBox
from PyQt5.QtCore import QThread, QObject, pyqtSignal, pyqtSlot, Qt
from src_physics.value_converter import ValueConverter
from src_physics.material import Material

class NumericTableWidgetItem(QTableWidgetItem):
    """QTableWidgetItem-Subklasse für korrekte numerische Sortierung"""
    def __init__(self, text, value):
        super().__init__(text)
        self.setData(Qt.UserRole, float(value))
        
    def __lt__(self, other):
        # Vergleich basierend auf dem tatsächlichen numerischen Wert
        return self.data(Qt.UserRole) < other.data(Qt.UserRole)

class OptimizationWorker(QObject):
    """Worker-Klasse für die Durchführung der Optimierung in einem separaten Thread"""
    finished = pyqtSignal(object)  # Signal mit Optimierungsergebnis
    error = pyqtSignal(str)      # Signal für Fehler
    progress = pyqtSignal(int)   # Signal für Fortschrittsanzeige (0-100)
    
    def __init__(self, optimizer, max_lenses, num_runs=100, total_generations=30):
        super().__init__()
        self.optimizer = optimizer
        self.max_lenses = max_lenses
        self.num_runs = num_runs
        self.total_generations = total_generations
        self.abort_flag = False
        
    @pyqtSlot()
    def run(self):
        """Führt die Multi-Run-Optimierung aus"""
        try:
            # Validiere Parameter
            if not self.optimizer.lens_library:
                self.error.emit("No lenses in library. Please select lenses first.")
                return
                
            max_lenses = max(1, self.max_lenses)
            
            if len(self.optimizer.lens_library) < 1:
                self.error.emit("Not enough lenses in library. Need at least 1 lens.")
                return
            
            # Führe Multi-Run-Optimierung durch
            result = self._run_multi_optimization(max_lenses, self.num_runs, self.total_generations)
            
            self.finished.emit(result)
            
        except Exception as e:
            self.error.emit(f"Error during optimization: {str(e)}")
    
    def _run_multi_optimization(self, max_lenses, num_runs, total_generations):
        """Multi-Run-Optimierung mit korrektem Progress-Tracking"""
        results = []
        best_result = None
        best_fitness = float('inf')

        self.optimizer.max_lenses = max_lenses
        self.optimizer.problem()

        seen_signatures = set()

        # Berechne Gesamtschritte für Progress
        total_steps = num_runs * total_generations
        current_step = 0

        # Adaptive Parameter basierend auf Linsenzahl
        base_pop_size = 50
        pop_size = min(100, base_pop_size + 10 * max_lenses)
        
        for run in range(num_runs):
            if self.abort_flag:
                break

            # Erstelle Population mit Diversität
            population = []
            for _ in range(pop_size):
                individual = self.optimizer.toolbox.individual()
                population.append(individual)
            
            # Berechne initiale Fitness
            for ind in population:
                fitness = self.optimizer.toolbox.evaluate(ind)
                ind.fitness.values = fitness
            
            stats = tools.Statistics(lambda ind: ind.fitness.values)
            stats.register("avg", np.mean)
            stats.register("min", np.min)
            stats.register("max", np.max)
            hof = tools.HallOfFame(3)

            # Adaptive Mutationsrate
            initial_mutation_rate = 0.3
            final_mutation_rate = 0.05
            
            for gen in range(total_generations):
                if self.abort_flag:
                    break
                
                # Update Progress
                current_step += 1
                progress_percent = int((current_step / total_steps) * 100)
                self.progress.emit(progress_percent)
                
                # Adaptive Parameter
                progress_gen = gen / total_generations
                current_mutation_rate = initial_mutation_rate * (1 - progress_gen) + final_mutation_rate * progress_gen
                crossover_rate = 0.7 - 0.2 * progress_gen
                
                # Evolution mit adaptiven Parametern
                offspring = algorithms.varAnd(population, self.optimizer.toolbox, crossover_rate, current_mutation_rate)
                
                # Bewerte Offspring
                fits = self.optimizer.toolbox.map(self.optimizer.toolbox.evaluate, offspring)
                for fit, ind in zip(fits, offspring):
                    ind.fitness.values = fit
                
                # Elitismus: Behalte beste Individuen
                combined_pop = population + offspring
                combined_pop.sort(key=lambda x: x.fitness.values[0])
                population = combined_pop[:pop_size]
                
                hof.update(population)

            if not self.abort_flag and hof:
                # Lokale Optimierung für alle Top-Kandidaten
                best_candidates = []
                for candidate in hof:
                    try:
                        optimized = self.optimizer._local_optimize(candidate)
                        best_candidates.append(optimized)
                    except Exception:
                        best_candidates.append(candidate)
                
                # Wähle besten Kandidaten
                best_candidates.sort(key=lambda x: x.fitness.values[0])
                best_individual = best_candidates[0]

                current_fitness = best_individual.fitness.values[0]
                waist_sag, waist_tan, position_sag, position_tan = self.optimizer.calculate_beam_parameters(best_individual)

                # Duplikate filtern
                sig = self._individual_signature(best_individual)
                if sig in seen_signatures:
                    continue
                seen_signatures.add(sig)

                result = {
                    'lenses': [(lens, pos) for lens, pos in best_individual],
                    'waist_sag': waist_sag,
                    'waist_tan': waist_tan,
                    'position_sag': position_sag,
                    'position_tan': position_tan,
                    'fitness': current_fitness,
                    'run': run + 1
                }
                results.append(result)

                if current_fitness < best_fitness:
                    best_result = result
                    best_fitness = current_fitness

        # Stelle sicher, dass Progress auf 100% steht
        self.progress.emit(100)
        return results
    
    def stop(self):
        """Bricht die Optimierung ab"""
        self.abort_flag = True

    def _individual_signature(self, individual, pos_digits=6, f_digits=9):
        """
        Erzeugt eine kanonische Signatur eines Individuums zur Duplikat-Erkennung.
        - Positionen gerundet (pos_digits)
        - Focal lengths zur Absicherung einbezogen
        """
        sig_parts = []
        for lens, pos in sorted(individual, key=lambda x: x[1]):
            props = lens.get('properties', {})
            f_sag = props.get('Focal length sagittal')
            f_tan = props.get('Focal length tangential')
            try:
                f_sag_r = round(float(f_sag), f_digits) if f_sag is not None else None
            except Exception:
                f_sag_r = None
            try:
                f_tan_r = round(float(f_tan), f_digits) if f_tan is not None else None
            except Exception:
                f_tan_r = None
            sig_parts.append((
                lens.get('name', ''),
                round(float(pos), pos_digits),
                f_sag_r,
                f_tan_r
            ))
        return tuple(sig_parts)

class LensSystemOptimizer:
    def __init__(self, matrices):
        self.matrices = matrices
        self.lens_library = []  # Wird dynamisch geladen
        self.vc = ValueConverter()
        self.material = Material
        
        # DEAP Setup entfernt - wird jetzt global in graycad_start.py gemacht
        self.toolbox = base.Toolbox()
        
        # Lade Linsenbibliothek aus temporärer Datei
        self._load_lens_library_from_temp_file()

    def _load_lens_library_from_temp_file(self):
        """Lade Linsenbibliothek aus der temporären Datei und füge für zylindrische Linsen auch die gedrehte Variante hinzu"""
        try:
            import copy
            temp_file_path = config.get_temp_file_path()
            if not temp_file_path:
                QMessageBox.critical(None, "Error", "Warning: No temp file path found, using default lens library")
                self._use_default_lens_library()
                return

            with open(temp_file_path, 'r') as file:
                data = json.load(file)

            components = data.get("components", [])
            self.lens_library = []

            for component in components:
                if component.get("type", "").upper() == "LENS":
                    properties = component.get("properties", {})
                    is_round = properties.get("IS_ROUND", True)

                    # Original hinzufügen
                    self.lens_library.append(component)

                    # Für zylindrische Linsen: gedrehte Variante hinzufügen
                    if not is_round:
                        swapped_component = copy.deepcopy(component)
                        swapped_properties = swapped_component["properties"]

                        # Vertausche sagittal/tangential für Focal length
                        if ("Focal length sagittal" in swapped_properties and
                            "Focal length tangential" in swapped_properties):
                            swapped_properties["Focal length sagittal"], swapped_properties["Focal length tangential"] = \
                                swapped_properties["Focal length tangential"], swapped_properties["Focal length sagittal"]

                        # Vertausche sagittal/tangential für Radius of curvature
                        if ("Radius of curvature sagittal" in swapped_properties and
                            "Radius of curvature tangential" in swapped_properties):
                            swapped_properties["Radius of curvature sagittal"], swapped_properties["Radius of curvature tangential"] = \
                                swapped_properties["Radius of curvature tangential"], swapped_properties["Radius of curvature sagittal"]

                        # Name anpassen
                        swapped_component["name"] = swapped_component.get("name", "") + " (rotated)"
                        self.lens_library.append(swapped_component)

        except Exception as e:
            QMessageBox.critical(None, "Error", f"Error loading lens library: {str(e)}")

    def plot_setup(self):
        """
        Erstellt eine Komponentenliste für das aktuelle Linsensystem und sendet sie an das Hauptfenster.
        Implementiert die korrekte Propagation zwischen Komponenten.
        """
        try:
            # Hole die aktuellen Strahlparameter
            wavelength = self.wavelength
            waist_sag = self.waist_input_sag
            waist_tan = self.waist_input_tan
            waist_pos_sag = self.waist_position_sag
            waist_pos_tan = self.waist_position_tan
            
            setup_components = []
            
            # 1. Beam-Komponente
            beam_component = {
                "type": "BEAM",
                "name": "Beam",
                "properties": {
                    "Wavelength": wavelength,
                    "Waist radius sagittal": waist_sag,
                    "Waist radius tangential": waist_tan,
                    "Waist position sagittal": waist_pos_sag,
                    "Waist position tangential": waist_pos_tan,
                    "Rayleigh range sagittal": np.pi * waist_sag**2 / wavelength,
                    "Rayleigh range tangential": np.pi * waist_tan**2 / wavelength,
                    "IS_ROUND": False
                }
            }
            setup_components.append(beam_component)

            # 2. Linsen-Komponenten mit korrekter Propagation
            if hasattr(self, "last_optimization_results") and self.last_optimization_results:
                best_result = min(self.last_optimization_results, key=lambda r: r['fitness'])
                # Sortiere Linsen nach Position
                sorted_lenses = sorted(best_result.get('lenses', []), key=lambda x: x[1])
                
                # Startposition für erste Propagation
                last_position = 0
                
                # Füge Propagationen und Linsen abwechselnd hinzu
                for lens, position in sorted_lenses:
                    # Berechne Propagationsdistanz zur nächsten Linse
                    prop_distance = position - last_position
                    
                    # Propagation zur Linsenposition
                    if prop_distance > 0:
                        prop_component = {
                            "type": "PROPAGATION",
                            "name": f"Propagation {last_position:.3f}m to {position:.3f}m",
                            "manufacturer": "",
                            "properties": {
                                "Length": prop_distance,
                                "Refractive index": 1.0
                            }
                        }
                        setup_components.append(prop_component)
                    
                    # Linse hinzufügen (ohne Position als Property)
                    lens_component = dict(lens)  # Kopiere die Komponente
                    setup_components.append(lens_component)
                    
                    # Aktualisiere letzte Position
                    last_position = position
                
                # Abschließende Propagation bis zum Ziel
                final_distance = self.distance - last_position
                if final_distance > 0:
                    final_prop = {
                        "type": "PROPAGATION",
                        "name": f"Propagation {last_position:.3f}m to {self.distance:.3f}m",
                        "properties": {
                            "Length": final_distance,
                            "Refractive index": 1.0
                        }
                    }
                    setup_components.append(final_prop)
                    
                # Falls zusätzlich eine Anzeige des Strahls am Zielort gewünscht ist
                # Hier könntest du eine Beam-out Komponente hinzufügen
            else:
                # Fallback: Keine Optimierungsergebnisse vorhanden
                QMessageBox.warning(None, "No Setup", "No optimized lens system available for plotting.")
                return

            # Übertrage das Setup an das Hauptfenster
            self._transfer_setup_to_mainwindow(setup_components)

            QMessageBox.information(None, "Setup Generated", f"Generated lens system setup with {len(setup_components)} components and fitness {best_result.get('fitness', 0):.4e}")

        except Exception as e:
            QMessageBox.critical(None, "Error", f"Error generating setup: {str(e)}")

    def get_beam_parameters(self):
        """Lade Strahlparameter aus der temporären Datei"""
        temp_data_modematcher = config.get_temp_data_modematcher()
        (self.wavelength, self.distance, self.waist_input_sag, self.waist_input_tan, 
        self.waist_position_sag, self.waist_position_tan, self.waist_goal_sag, 
        self.waist_goal_tan, self.waist_position_goal_sag, self.waist_position_goal_tan) = temp_data_modematcher

    def safe_crossover(self, ind1, ind2):
        """Sicherer Crossover für Individuen beliebiger Länge"""
        # For very short individuals, just swap them entirely
        if len(ind1) <= 1 or len(ind2) <= 1:
            ind1[:], ind2[:] = ind2[:], ind1[:]
            return ind1, ind2
            
        # For longer individuals, use two-point crossover
        try:
            return tools.cxTwoPoint(ind1, ind2)
        except Exception:
            # Fallback: swap random lens between individuals
            if len(ind1) > 0 and len(ind2) > 0:
                idx1 = random.randint(0, len(ind1) - 1)
                idx2 = random.randint(0, len(ind2) - 1)
                ind1[idx1], ind2[idx2] = ind2[idx2], ind1[idx1]
            return ind1, ind2

    def problem(self):
        """Erstelle das Problem-Objekt abhängig von der Anzahl der Linsen"""
        # Check if FitnessMin and Individual already exist in creator
        if not hasattr(creator, "FitnessMin"):
            creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
        
        if not hasattr(creator, "Individual"):
            creator.create("Individual", list, fitness=creator.FitnessMin)
        
        # Register the individual creation strategy
        self.toolbox.register("individual", self.build_individual)
        self.toolbox.register("population", tools.initRepeat, list, self.toolbox.individual)
        
        # Register genetic operators
        self.toolbox.register("evaluate", self.fitness_function)
        # Use our safe crossover instead of standard cxTwoPoint
        self.toolbox.register("mate", self.safe_crossover)
        self.toolbox.register("mutate", self.mutate_lens_system, indpb=0.2)
        self.toolbox.register("select", tools.selTournament, tournsize=3)
    
    def build_individual(self):
        """Erstelle ein neues Individuum (Linsensystem)"""
        individual = []
        
        # Zufällige Anzahl von Linsen (1 bis max_lenses)
        if self.max_lenses > 1:
            num_lenses = random.randint(1, self.max_lenses)
        else:
            # If max_lenses is 1, don't use randint
            num_lenses = 1
        
        # Für jede Linse: wähle eine zufällige Linse aus der Bibliothek und eine zufällige Position
        total_distance = self.distance  # Gesamtdistanz zwischen Eingangs- und Zielstrahl
        
        # FIX: Check if lens library is not empty
        if not self.lens_library:
            raise ValueError("Lens library is empty. Cannot create individuals.")
            
        for _ in range(num_lenses):
            # Wähle zufällige Linse
            lens = random.choice(self.lens_library)
            # Wähle zufällige Position (0 bis total_distance)
            position = random.uniform(0, total_distance)
            # Füge Linse und Position zum Individual hinzu
            individual.append((lens, position))
        
        # Sortiere Linsen nach Position
        individual.sort(key=lambda x: x[1])
        
        return creator.Individual(individual)
    
    def mutate_lens_system(self, individual, indpb):
        """Mutiere ein Linsensystem durch Ändern der Linsen oder Positionen"""
        # FIX: Check if lens library is not empty
        if not self.lens_library:
            return individual,
            
        for i in range(len(individual)):
            # Mit Wahrscheinlichkeit indpb, ändere die Linse
            if random.random() < indpb:
                individual[i] = (random.choice(self.lens_library), individual[i][1])
            
            # Mit Wahrscheinlichkeit indpb, ändere die Position
            if random.random() < indpb:
                individual[i] = (individual[i][0], random.uniform(0, self.distance))
        
        # Sortiere Linsen nach Position
        individual.sort(key=lambda x: x[1])
        return individual,
    
    def calculate_beam_parameters(self, individual):
        """Berechne die resultierenden Strahlparameter für ein gegebenes Linsensystem"""
        # Beam-Objekt erstellen
        beam = Beam()
        
        # Initialisiere mit den Eingangsparametern
        n = 1.0  # Brechungsindex von Luft
        
        # Berechne q-Parameter für sagittal und tangential
        q_sag = beam.q_value(self.waist_position_sag, self.waist_input_sag, self.wavelength, n)
        q_tan = beam.q_value(self.waist_position_tan, self.waist_input_tan, self.wavelength, n)
        
        # Sortiere Linsensystem nach Position
        sorted_system = sorted(individual, key=lambda x: x[1])
        
        # Optisches System aufbauen
        last_position = 0
        elements_sag = []
        elements_tan = []
        
        for lens, position in sorted_system:
            # Freie Propagation zur Linsenposition
            distance = position - last_position
            if distance > 0:
                elements_sag.append((beam.matrices.free_space, (distance, n)))
                elements_tan.append((beam.matrices.free_space, (distance, n)))
            
            # Extrahiere Brennweiten für beide Ebenen
            f_sag, f_tan = self._get_lens_focal_lengths(lens)
            
            # Linseneffekt hinzufügen - berücksichtige unterschiedliche Brennweiten
            if f_sag is not None and f_sag != float('inf'):
                elements_sag.append((beam.matrices.lens, (f_sag,)))
            
            if f_tan is not None and f_tan != float('inf'):
                elements_tan.append((beam.matrices.lens, (f_tan,)))
            
            # Position aktualisieren
            last_position = position
        
        # Propagation zum Ziel
        final_distance = self.distance - last_position
        if final_distance > 0:
            elements_sag.append((beam.matrices.free_space, (final_distance, n)))
            elements_tan.append((beam.matrices.free_space, (final_distance, n)))
        
        # Propagiere q-Parameter durch das System
        q_sag_final = q_sag
        q_tan_final = q_tan
        
        # Propagation durch jedes Element
        for element, params in elements_sag:
            if callable(element):
                abcd_matrix = element(*params)
                q_sag_final = beam.propagate_q(q_sag_final, abcd_matrix)
        
        for element, params in elements_tan:
            if callable(element):
                abcd_matrix = element(*params)
                q_tan_final = beam.propagate_q(q_tan_final, abcd_matrix)
        
        def get_w0_and_focus(q_final, z_out):
            """
            Berechnet die minimale Strahltaille w₀ und Fokusposition nach einer ABCD-Kette.
            q_final: q-Parameter am Systemende
            z_out: absolute Position am Systemende (z.B. self.distance)
            """
            n = 1.0
            zR = np.imag(q_final)
            if zR <= 0:
                return float('inf'), float('nan')
            w0 = np.sqrt(self.wavelength * zR / (np.pi * n))
            # Fokusposition relativ zum Systemstart:
            focus_position = z_out - np.real(q_final)
            return w0, focus_position
        
        # Berechne echte w₀-Werte
        w0_sag, focus_pos_sag = get_w0_and_focus(q_sag_final, self.distance)
        w0_tan, focus_pos_tan = get_w0_and_focus(q_tan_final, self.distance)
        
        return w0_sag, w0_tan, focus_pos_sag, focus_pos_tan

    def _get_lens_focal_lengths(self, lens):
        """Extrahiere sagittale und tangentiale Brennweite einer Linse aus JSON-Komponente"""
        properties = lens.get('properties', {})
        design_wavelength = properties.get('Design wavelength')
        lens_material = properties.get('Lens material')
        n_design = self.material.get_n(lens_material, design_wavelength)
        n = self.material.get_n(lens_material, self.wavelength)
        f_design_sag = properties.get('Focal length sagittal')
        f_design_tan = properties.get('Focal length tangential')
        f_sag = ((n_design-1)/(n-1)) * f_design_sag
        f_tan = ((n_design-1)/(n-1)) * f_design_tan

        # Fallback: Wenn nur eine Brennweite existiert, beide gleich setzen
        if f_sag is None and f_tan is not None:
            f_sag = f_tan
        if f_tan is None and f_sag is not None:
            f_tan = f_sag

        # Konvertiere zu float, falls möglich
        try:
            f_sag = float(f_sag) if f_sag is not None else None
            f_tan = float(f_tan) if f_tan is not None else None
        except (ValueError, TypeError):
            f_sag = f_tan = None

        # Prüfe auf unendliche oder sehr große Werte
        if f_sag is not None and (f_sag > 1e20 or f_sag == float('inf')):
            f_sag = float('inf')
        if f_tan is not None and (f_tan > 1e20 or f_tan == float('inf')):
            f_tan = float('inf')

        return f_sag, f_tan
    
    def fitness_function(self, individual):
        """Berechne Fitness für ein gegebenes Individuum"""
        # Berechne resultierende Strahlparameter
        w0_sag, w0_tan, focus_pos_sag, focus_pos_tan = self.calculate_beam_parameters(individual)

        # Berechne Abweichung von Zielparametern
        rel_waist_error_sag = abs(self.waist_goal_sag - w0_sag)/(abs(self.waist_goal_sag))
        rel_waist_error_tan = abs(self.waist_goal_tan - w0_tan)/(abs(self.waist_goal_tan))
        
        fitness_waist = rel_waist_error_sag + rel_waist_error_tan

        # Normalisierte Positionsabweichung (Fokusposition)
        target_pos_sag = self.distance + self.waist_position_goal_sag
        target_pos_tan = self.distance + self.waist_position_goal_tan

        offset_sag = 1 - abs(target_pos_sag) / (1 + abs(focus_pos_sag))
        offset_tan = 1 - abs(target_pos_tan) / (1 + abs(focus_pos_tan))

        rel_pos_error_sag = abs(target_pos_sag - focus_pos_sag) / (abs(target_pos_sag) + abs(focus_pos_sag) + offset_sag)
        rel_pos_error_tan = abs(target_pos_tan - focus_pos_tan) / (abs(target_pos_tan) + abs(focus_pos_tan) + offset_tan)

        fitness_position = rel_pos_error_sag + rel_pos_error_tan

        # Gewichtung zwischen Strahlgröße und Position
        try:
            weight = self.ui_modematcher_calculation.weight_slider.value() / 100.0
        except AttributeError:
            weight = 0.5

        fitness = ((1 - weight) * fitness_waist) + (weight * fitness_position)

        return (fitness,)
    
    def optimize_lens_system(self, max_lenses, num_runs=100, total_generation=60):
        """Startet die Multi-Run-Optimierung in einem separaten Thread"""
        self.get_beam_parameters()
        self._load_lens_library_from_temp_file()
        
        try:
            # Validierungen
            if not self.lens_library:
                raise ValueError("No lenses in library. Please select lenses first.")
                
            if len(self.lens_library) < 1:
                raise ValueError("Not enough lenses in library. Need at least 1 lens.")
            
            # Erstelle Thread und Worker-Objekt
            self.thread = QThread()
            self.worker = OptimizationWorker(self, max_lenses, num_runs)
            
            # Verschiebe Worker in Thread
            self.worker.moveToThread(self.thread)
            
            # Verbinde nur interne Signale
            self.thread.started.connect(self.worker.run)
            self.worker.finished.connect(self.thread.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.thread.finished.connect(self.thread.deleteLater)
            
            # Starte Thread
            self.thread.start()
            
            # Gib Worker zurück für externe Signal-Verbindungen
            return self.worker
            
        except Exception as e:
            raise Exception(f"Error setting up optimization: {str(e)}")
    
    def _local_optimize(self, best_individual):
        """Führt eine lokale Optimierung der Linsenpositionen durch"""
        # Extrahiere nur die Positionen für die Optimierung
        initial_positions = np.array([pos for _, pos in best_individual])
        
        # Definiere Grenzen (0 bis self.distance)
        bounds = [(0, self.distance) for _ in range(len(initial_positions))]
        
        # Fitness-Funktion für lokale Optimierung
        def position_fitness(positions):
            # Erstelle neues Individuum mit optimierten Positionen
            new_individual = [(lens, pos) for (lens, _), pos in zip(best_individual, positions)]
            # Sortiere nach Position
            new_individual.sort(key=lambda x: x[1])
            # Berechne Fitness
            return self.fitness_function(new_individual)[0]
        
        # Führe lokale Optimierung durch
        result = minimize(
            position_fitness,
            initial_positions,
            method='L-BFGS-B',
            bounds=bounds,
            options={'maxiter': 100, 'disp': False}
        )
        
        # Erstelle optimiertes Individuum als neue Liste
        optimized_list = [(lens, pos) for (lens, _), pos in zip(best_individual, result.x)]
        # Sortiere nach Position
        optimized_list.sort(key=lambda x: x[1])
        
        # Konvertiere zu einem DEAP Individual-Objekt
        optimized_individual = creator.Individual(optimized_list)
        
        # Berechne und setze Fitness
        fitness_value = self.fitness_function(optimized_individual)
        optimized_individual.fitness.values = fitness_value
        
        return optimized_individual
    
    def stop_optimization(self):
        """Stoppe die Optimierung"""
        try:
            # Stoppe den Worker im Optimizer, falls vorhanden
            if hasattr(self, 'worker') and self.worker is not None:
                self.worker.stop()
            # Beende ggf. den Thread
            if hasattr(self, 'thread') and self.thread is not None:
                self.thread.quit()
                self.thread.wait()
            # Setze UI zurück, falls möglich
            if hasattr(self, 'ui_modematcher_calculation') and hasattr(self.ui_modematcher_calculation, 'progressBar'):
                self.ui_modematcher_calculation.progressBar.setValue(0)
                if hasattr(self.ui_modematcher_calculation, 'button_optimize'):
                    self.ui_modematcher_calculation.button_optimize.setEnabled(True)
        except Exception as e:
            # QMessageBox braucht als erstes Argument ein QWidget oder None!
            QMessageBox.critical(None, "Error", "Error stopping optimization: " + str(e))