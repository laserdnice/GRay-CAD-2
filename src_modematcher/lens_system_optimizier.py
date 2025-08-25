import numpy as np
from scipy.optimize import least_squares
from src_physics.beam import Beam
import random
import json
import config
from PyQt5.QtWidgets import QMessageBox, QProgressDialog, QApplication, QTableWidgetItem, QCheckBox
from PyQt5.QtCore import QThread, QObject, pyqtSignal, pyqtSlot, Qt
from src_physics.value_converter import ValueConverter
from src_physics.material import Material
import itertools
import multiprocessing as mp
from functools import partial
import os

class NumericTableWidgetItem(QTableWidgetItem):
    """QTableWidgetItem-Subklasse für korrekte numerische Sortierung"""
    def __init__(self, text, value):
        super().__init__(text)
        self.setData(Qt.UserRole, float(value))
        
    def __lt__(self, other):
        # Vergleich basierend auf dem tatsächlichen numerischen Wert
        return self.data(Qt.UserRole) < other.data(Qt.UserRole)

def optimize_single_combination(combination_data):
    """
    Standalone-Funktion für die Optimierung einer einzelnen Linsenkombination.
    Verwendet Abstände (auch negative) als Optimierungsparameter für automatische Permutationen.
    """
    lens_combination, optimizer_params = combination_data
    
    try:
        # Optimizer-Parameter entpacken
        wavelength = optimizer_params['wavelength']
        distance = optimizer_params['distance']
        waist_input_sag = optimizer_params['waist_input_sag']
        waist_input_tan = optimizer_params['waist_input_tan']
        waist_position_sag = optimizer_params['waist_position_sag']
        waist_position_tan = optimizer_params['waist_position_tan']
        waist_goal_sag = optimizer_params['waist_goal_sag']
        waist_goal_tan = optimizer_params['waist_goal_tan']
        waist_position_goal_sag = optimizer_params['waist_position_goal_sag']
        waist_position_goal_tan = optimizer_params['waist_position_goal_tan']
        weight = optimizer_params.get('weight', 0.5)
        
        def get_lens_focal_lengths_standalone(lens, wavelength):
            """Standalone-Version der Brennweiten-Berechnung - IDENTISCH zur Klassen-Methode"""
            from src_physics.material import Material
            
            material = Material
            properties = lens.get('properties', {})
            design_wavelength = properties.get('Design wavelength')
            lens_material = properties.get('Lens material')
            
            try:
                n_design = material.get_n(lens_material, design_wavelength)
                n = material.get_n(lens_material, wavelength)
                f_design_sag = properties.get('Focal length sagittal')
                f_design_tan = properties.get('Focal length tangential')
                
                # WICHTIG: Wellenlängen-Korrektur!
                f_sag = ((n_design-1)/(n-1)) * f_design_sag if f_design_sag is not None else None
                f_tan = ((n_design-1)/(n-1)) * f_design_tan if f_design_tan is not None else None
            except:
                QMessageBox.critical(None, "Error", "Failed to calculate lens focal lengths.")

            # Prüfe auf unendliche oder sehr große Werte
            if f_sag is not None and (f_sag > 1e20 or f_sag == float('inf')):
                f_sag = float('inf')
            if f_tan is not None and (f_tan > 1e20 or f_tan == float('inf')):
                f_tan = float('inf')

            return f_sag, f_tan
        
        def distances_to_positions_and_order(distances):
            """
            Konvertiert Abstände zu absoluten Positionen und bestimmt die Reihenfolge.
            Negative Abstände bedeuten: diese Linse kommt VOR die vorherige.
            """
            lens_positions = []
            current_pos = 0
            
            for i, (lens, dist) in enumerate(zip(lens_combination, distances)):
                if dist >= 0:
                    # Positive Distanz: normale Reihenfolge
                    current_pos += dist
                    lens_positions.append((lens, current_pos, i))
                else:
                    # Negative Distanz: diese Linse kommt vor die letzte Position
                    current_pos += dist  # dist ist negativ, also wird subtrahiert
                    if current_pos < 0:
                        current_pos = abs(dist) * 0.1  # Mindestabstand vom Start
                    lens_positions.append((lens, current_pos, i))
            
            # Sortiere nach Position (automatische Permutation!)
            lens_positions.sort(key=lambda x: x[1])
            
            # Extrahiere sortierte Linsen und Positionen
            sorted_lenses = [item[0] for item in lens_positions]
            sorted_positions = [item[1] for item in lens_positions]
            
            return sorted_lenses, sorted_positions
        
        def calculate_beam_parameters_standalone(distances, lens_combination, optimizer_params):
            """Standalone-Version der Strahlberechnung mit automatischer Permutation"""
            from src_physics.beam import Beam
            
            beam = Beam()
            
            # Parameter aus optimizer_params
            wavelength = optimizer_params['wavelength']
            distance = optimizer_params['distance']
            waist_position_sag = optimizer_params['waist_position_sag']
            waist_position_tan = optimizer_params['waist_position_tan']
            waist_input_sag = optimizer_params['waist_input_sag']
            waist_input_tan = optimizer_params['waist_input_tan']
            
            n = 1.0  # Brechungsindex von Luft
            
            # Konvertiere Abstände zu sortierter Reihenfolge
            sorted_lenses, sorted_positions = distances_to_positions_and_order(distances)
            
            # Prüfe, dass alle Positionen im erlaubten Bereich sind
            if any(pos <= 0 or pos >= distance for pos in sorted_positions):
                return float('inf'), float('inf'), float('nan'), float('nan')
            
            # Berechne q-Parameter für sagittal und tangential
            q_sag = beam.q_value(waist_position_sag, waist_input_sag, wavelength, n)
            q_tan = beam.q_value(waist_position_tan, waist_input_tan, wavelength, n)
            
            # Optisches System aufbauen mit automatisch sortierter Reihenfolge
            last_position = 0
            elements_sag = []
            elements_tan = []
            
            for lens, position in zip(sorted_lenses, sorted_positions):
                # Freie Propagation zur Linsenposition
                distance_prop = position - last_position
                if distance_prop > 0:
                    elements_sag.append((beam.matrices.free_space, (distance_prop, n)))
                    elements_tan.append((beam.matrices.free_space, (distance_prop, n)))
                elif distance_prop < 0:
                    # Das sollte nach der Sortierung nicht passieren
                    return float('inf'), float('inf'), float('nan'), float('nan')
                
                # WICHTIG: Verwende die korrekte Brennweiten-Berechnung!
                f_sag, f_tan = get_lens_focal_lengths_standalone(lens, wavelength)
                
                # Linseneffekt hinzufügen
                if f_sag is not None and f_sag != float('inf') and f_sag != 0:
                    elements_sag.append((beam.matrices.lens, (float(f_sag),)))
                
                if f_tan is not None and f_tan != float('inf') and f_tan != 0:
                    elements_tan.append((beam.matrices.lens, (float(f_tan),)))
                
                last_position = position
            
            # Propagation zum Ziel
            final_distance = distance - last_position
            if final_distance > 0:
                elements_sag.append((beam.matrices.free_space, (final_distance, n)))
                elements_tan.append((beam.matrices.free_space, (final_distance, n)))
            elif final_distance < 0:
                return float('inf'), float('inf'), float('nan'), float('nan')
            
            # Propagiere q-Parameter durch das System
            q_sag_final = q_sag
            q_tan_final = q_tan
            
            for element, params in elements_sag:
                if callable(element):
                    abcd_matrix = element(*params)
                    q_sag_final = beam.propagate_q(q_sag_final, abcd_matrix)
            
            for element, params in elements_tan:
                if callable(element):
                    abcd_matrix = element(*params)
                    q_tan_final = beam.propagate_q(q_tan_final, abcd_matrix)
            
            def get_w0_and_focus(q_final, z_out):
                n = 1.0
                zR = np.imag(q_final)
                if zR <= 0:
                    return float('inf'), float('nan')
                w0 = np.sqrt(wavelength * zR / (np.pi * n))
                focus_position = z_out - np.real(q_final)
                return w0, focus_position
            
            w0_sag, focus_pos_sag = get_w0_and_focus(q_sag_final, distance)
            w0_tan, focus_pos_tan = get_w0_and_focus(q_tan_final, distance)
            
            return w0_sag, w0_tan, focus_pos_sag, focus_pos_tan
        
        def calculate_residuals_standalone(distances, lens_combination, optimizer_params):
            """Standalone-Version der Residuen-Berechnung mit automatischer Permutation"""
            try:
                waist_sag, waist_tan, position_sag, position_tan = calculate_beam_parameters_standalone(
                    distances, lens_combination, optimizer_params
                )
                
                if (np.isnan(waist_sag) or np.isnan(waist_tan) or 
                    np.isnan(position_sag) or np.isnan(position_tan) or
                    waist_sag <= 0 or waist_tan <= 0 or
                    waist_sag == float('inf') or waist_tan == float('inf')):
                    return np.array([1e6, 1e6, 1e6, 1e6])
                
                # Zielwerte
                target_pos_sag = optimizer_params['distance'] + optimizer_params['waist_position_goal_sag']
                target_pos_tan = optimizer_params['distance'] + optimizer_params['waist_position_goal_tan']
                
                # Normalisierte Residuen
                waist_error_sag = (waist_sag - optimizer_params['waist_goal_sag']) / optimizer_params['waist_goal_sag']
                waist_error_tan = (waist_tan - optimizer_params['waist_goal_tan']) / optimizer_params['waist_goal_tan']
                
                pos_norm_sag = max(abs(target_pos_sag), abs(position_sag), 1e-6)
                pos_norm_tan = max(abs(target_pos_tan), abs(position_tan), 1e-6)
                
                pos_error_sag = (position_sag - target_pos_sag) / pos_norm_sag
                pos_error_tan = (position_tan - target_pos_tan) / pos_norm_tan
                
                # Gewichtung
                weight = optimizer_params.get('weight', 0.5)
                waist_weight = np.sqrt(1 - weight)
                pos_weight = np.sqrt(weight)
                
                return np.array([
                    waist_weight * waist_error_sag,
                    waist_weight * waist_error_tan,
                    pos_weight * pos_error_sag,
                    pos_weight * pos_error_tan
                ])
                
            except Exception:
                return np.array([1e6, 1e6, 1e6, 1e6])
        
        # Optimierung für diese Kombination
        num_lenses = len(lens_combination)
        best_result = None
        best_fitness = float('inf')
        
        num_starts = min(3, max(1, 6 // num_lenses))
        
        for start_attempt in range(num_starts):
            try:
                if start_attempt == 0:
                    # Gleichmäßig verteilte positive Abstände
                    initial_distances = np.full(num_lenses, distance / (num_lenses + 1))
                elif start_attempt == 1:
                    # Mischung aus positiven und negativen Abständen
                    initial_distances = np.random.uniform(-distance/4, distance/2, num_lenses)
                else:
                    # Weitere zufällige Variationen
                    initial_distances = np.random.uniform(-distance/3, distance/3, num_lenses)
                
                # Test der Residuen-Funktion
                test_residuals = calculate_residuals_standalone(initial_distances, lens_combination, optimizer_params)
                if np.any(np.abs(test_residuals) > 1e5):
                    continue
                
                # Grenzen für Abstände: können jetzt auch negativ sein
                max_abs_dist = distance * 0.8  # Maximaler Absolutwert
                bounds = ([-max_abs_dist] * num_lenses, [max_abs_dist] * num_lenses)
                
                result = least_squares(
                    lambda dist: calculate_residuals_standalone(dist, lens_combination, optimizer_params),
                    initial_distances,
                    bounds=bounds,
                    method='trf',
                    max_nfev=100,
                    ftol=1e-12,
                    xtol=1e-12,
                    gtol=1e-12
                )
                
                if result.success or result.cost < best_fitness:
                    final_fitness = np.sum(result.fun**2)
                    
                    if final_fitness < best_fitness:
                        best_fitness = final_fitness
                        
                        # Konvertiere zu Individual mit finaler Reihenfolge
                        sorted_lenses, sorted_positions = distances_to_positions_and_order(result.x)
                        individual = [(lens, pos) for lens, pos in zip(sorted_lenses, sorted_positions)]
                        
                        waist_sag, waist_tan, position_sag, position_tan = calculate_beam_parameters_standalone(
                            result.x, lens_combination, optimizer_params
                        )
                        
                        if (not np.isnan(waist_sag) and not np.isnan(waist_tan) and 
                            not np.isnan(position_sag) and not np.isnan(position_tan) and
                            waist_sag > 0 and waist_tan > 0 and 
                            waist_sag != float('inf') and waist_tan != float('inf')):
                            
                            best_result = {
                                'lenses': individual,
                                'waist_sag': waist_sag,
                                'waist_tan': waist_tan,
                                'position_sag': position_sag,
                                'position_tan': position_tan,
                                'fitness': final_fitness,
                                'combination': lens_combination
                            }
                            
            except Exception:
                continue
        
        return best_result
        
    except Exception:
        return None

class OptimizationWorker(QObject):
    """Worker-Klasse für die Durchführung der Optimierung in einem separaten Thread"""
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)
    
    def __init__(self, optimizer, max_lenses, num_runs=100, total_generations=30):
        super().__init__()
        self.optimizer = optimizer
        self.max_lenses = max_lenses
        self.num_runs = num_runs
        self.total_generations = total_generations
        self.abort_flag = False
        
    @pyqtSlot()
    def run(self):
        """Führt die parallelisierte Kombinationsoptimierung aus"""
        try:
            if not self.optimizer.lens_library:
                self.error.emit("No lenses in library. Please select lenses first.")
                return
                
            max_lenses = max(1, self.max_lenses)
            
            if len(self.optimizer.lens_library) < 1:
                self.error.emit("Not enough lenses in library. Need at least 1 lens.")
                return
            
            result = self._run_parallel_optimization(max_lenses)
            self.finished.emit(result)
            
        except Exception as e:
            self.error.emit(f"Error during optimization: {str(e)}")
    
    def _run_parallel_optimization(self, max_lenses):
        """Parallelisierte Optimierung mit multiprocessing"""
        results = []
        seen_signatures = set()
        
        # Generiere alle Kombinationen
        all_combinations = list(itertools.combinations_with_replacement(
            self.optimizer.lens_library, max_lenses
        ))
        
        total_combinations = len(all_combinations)
        
        # Optimizer-Parameter für Worker-Prozesse
        optimizer_params = {
            'wavelength': self.optimizer.wavelength,
            'distance': self.optimizer.distance,
            'waist_input_sag': self.optimizer.waist_input_sag,
            'waist_input_tan': self.optimizer.waist_input_tan,
            'waist_position_sag': self.optimizer.waist_position_sag,
            'waist_position_tan': self.optimizer.waist_position_tan,
            'waist_goal_sag': self.optimizer.waist_goal_sag,
            'waist_goal_tan': self.optimizer.waist_goal_tan,
            'waist_position_goal_sag': self.optimizer.waist_position_goal_sag,
            'waist_position_goal_tan': self.optimizer.waist_position_goal_tan,
            'weight': 0.5  # Fallback-Gewichtung
        }
        
        # Gewichtung aus UI holen, falls verfügbar
        try:
            if hasattr(self.optimizer, 'ui_modematcher_calculation'):
                optimizer_params['weight'] = self.optimizer.ui_modematcher_calculation.weight_slider.value() / 100.0
        except:
            pass
        
        # Anzahl Prozessorkerne
        num_cores = min(mp.cpu_count(), len(all_combinations))
        num_cores = max(1, num_cores - 1)  # Einen Kern für UI freilassen
        
        # Daten für Worker vorbereiten
        combination_data = [(combo, optimizer_params) for combo in all_combinations]
        
        # Parallelisierung mit Pool
        if num_cores > 1:
            try:
                with mp.Pool(processes=num_cores) as pool:
                    # Progress-Tracking mit imap
                    completed = 0
                    for result in pool.imap(optimize_single_combination, combination_data):
                        if self.abort_flag:
                            pool.terminate()
                            break
                            
                        completed += 1
                        progress_percent = int((completed / total_combinations) * 100)
                        self.progress.emit(progress_percent)
                        
                        if result is not None:
                            # Duplikate filtern
                            sig = self._combination_signature(result)
                            if sig not in seen_signatures:
                                seen_signatures.add(sig)
                                results.append(result)
                                
            except Exception as e:
                # Fallback auf sequenzielle Verarbeitung
                self.error.emit(f"Parallel processing failed, falling back to sequential: {str(e)}")
                return self._run_sequential_optimization(max_lenses)
        else:
            # Sequenzielle Verarbeitung für wenige Kombinationen
            return self._run_sequential_optimization(max_lenses)
        
        # Sortiere Ergebnisse nach Fitness
        results.sort(key=lambda x: x['fitness'])
        self.progress.emit(100)
        return results
    
    def _run_sequential_optimization(self, max_lenses):
        """Fallback: Sequenzielle Optimierung"""
        results = []
        seen_signatures = set()
        
        all_combinations = list(itertools.combinations_with_replacement(
            self.optimizer.lens_library, max_lenses
        ))
        
        total_combinations = len(all_combinations)
        current_combination = 0
        
        for lens_combination in all_combinations:
            if self.abort_flag:
                break
                
            current_combination += 1
            progress_percent = int((current_combination / total_combinations) * 100)
            self.progress.emit(progress_percent)
            
            try:
                optimized_result = self._optimize_positions_for_combination(lens_combination)
                
                if optimized_result is not None:
                    sig = self._combination_signature(optimized_result)
                    if sig not in seen_signatures:
                        seen_signatures.add(sig)
                        results.append(optimized_result)
                        
            except Exception:
                continue
        
        results.sort(key=lambda x: x['fitness'])
        self.progress.emit(100)
        return results
    
    def _optimize_positions_for_combination(self, lens_combination):
        """Optimiert die Positionen für eine gegebene Linsenkombination mit Levenberg-Marquardt"""
        num_lenses = len(lens_combination)
        
        # Mehrere Startpunkte ausprobieren für bessere Konvergenz
        best_result = None
        best_fitness = float('inf')
        
        num_starts = min(5, max(1, 10 // num_lenses))  # Weniger Starts für mehr Linsen
        
        for start_attempt in range(num_starts):
            try:
                # Zufällige Startpositionen
                if start_attempt == 0:
                    # Erster Versuch: gleichmäßig verteilte Positionen
                    initial_positions = np.linspace(0.1 * self.optimizer.distance, 
                                                  0.9 * self.optimizer.distance, 
                                                  num_lenses)
                else:
                    # Weitere Versuche: zufällige Positionen
                    initial_positions = np.sort(np.random.uniform(
                        0, self.optimizer.distance, num_lenses
                    ))
                
                # Definiere Residuen-Funktion für LM
                def residuals(positions):
                    return self._calculate_residuals(lens_combination, positions)
                
                # Test ob Residuen-Funktion funktioniert
                test_residuals = residuals(initial_positions)
                if np.any(np.abs(test_residuals) > 1e5):
                    continue
                
                # Grenzen für Positionen
                bounds = ([0] * num_lenses, [self.optimizer.distance] * num_lenses)
                
                # Levenberg-Marquardt Optimierung
                result = least_squares(
                    residuals,
                    initial_positions,
                    bounds=bounds,
                    method='trf',
                    max_nfev=1000,
                    ftol=1e-12,
                    xtol=1e-12,
                    gtol=1e-12
                )
                
                if result.success or result.cost < best_fitness:  # Auch bei nicht-convergence gute Ergebnisse nehmen
                    # Berechne finale Fitness
                    final_fitness = np.sum(result.fun**2)
                    
                    if final_fitness < best_fitness:
                        best_fitness = final_fitness
                        
                        # Berechne Strahlparameter
                        individual = [(lens, pos) for lens, pos in zip(lens_combination, result.x)]
                        waist_sag, waist_tan, position_sag, position_tan = self.optimizer.calculate_beam_parameters(individual)
                        
                        # Prüfe auf gültige Ergebnisse
                        if (not np.isnan(waist_sag) and not np.isnan(waist_tan) and 
                            not np.isnan(position_sag) and not np.isnan(position_tan) and
                            waist_sag > 0 and waist_tan > 0):
                            
                            best_result = {
                                'lenses': individual,
                                'waist_sag': waist_sag,
                                'waist_tan': waist_tan,
                                'position_sag': position_sag,
                                'position_tan': position_tan,
                                'fitness': final_fitness,
                                'combination': lens_combination
                            }
                            
            except Exception as e:
                continue
        
        return best_result
    
    def _calculate_residuals(self, lens_combination, positions):
        """Berechnet Residuen für die LM-Optimierung"""
        try:
            # Erstelle Individual aus Kombination und Positionen
            individual = [(lens, pos) for lens, pos in zip(lens_combination, positions)]
            
            # Berechne Strahlparameter
            waist_sag, waist_tan, position_sag, position_tan = self.optimizer.calculate_beam_parameters(individual)
            
            # Prüfe auf ungültige Werte
            if (np.isnan(waist_sag) or np.isnan(waist_tan) or 
                np.isnan(position_sag) or np.isnan(position_tan) or
                waist_sag <= 0 or waist_tan <= 0):
                return np.array([1e6, 1e6, 1e6, 1e6])
            
            # Berechne Residuen (Abweichungen von Zielwerten)
            target_pos_sag = self.optimizer.distance + self.optimizer.waist_position_goal_sag
            target_pos_tan = self.optimizer.distance + self.optimizer.waist_position_goal_tan
            
            # Normalisierte Residuen
            waist_error_sag = (waist_sag - self.optimizer.waist_goal_sag) / self.optimizer.waist_goal_sag
            waist_error_tan = (waist_tan - self.optimizer.waist_goal_tan) / self.optimizer.waist_goal_tan
            
            # Positionsfehler normalisiert
            pos_norm_sag = max(abs(target_pos_sag), abs(position_sag), 1e-6)
            pos_norm_tan = max(abs(target_pos_tan), abs(position_tan), 1e-6)
            
            pos_error_sag = (position_sag - target_pos_sag) / pos_norm_sag
            pos_error_tan = (position_tan - target_pos_tan) / pos_norm_tan

            # Gewichtung zwischen Strahlgröße und Position
            try:
                weight = self.optimizer.ui_modematcher_calculation.weight_slider.value() / 100.0
            except AttributeError:
                weight = 0.5
            
            # Rückgabe als Array von Residuen
            waist_weight = np.sqrt(1 - weight)
            pos_weight = np.sqrt(weight)
            
            residuals = np.array([
                waist_weight * waist_error_sag,
                waist_weight * waist_error_tan,
                pos_weight * pos_error_sag,
                pos_weight * pos_error_tan
            ])
            
            return residuals
            
        except Exception as e:
            # Bei Fehlern: große Residuen zurückgeben
            return np.array([1e6, 1e6, 1e6, 1e6])
    
    def stop(self):
        """Bricht die Optimierung ab"""
        self.abort_flag = True

    def _combination_signature(self, result, pos_digits=6):
        """Erzeugt eine Signatur für eine Linsenkombination"""
        lenses = result.get('lenses', [])
        sig_parts = []
        for lens, pos in sorted(lenses, key=lambda x: x[1]):
            props = lens.get('properties', {})
            f_sag = props.get('Focal length sagittal')
            f_tan = props.get('Focal length tangential')
            sig_parts.append((
                lens.get('name', ''),
                round(float(pos), pos_digits),
                f_sag,
                f_tan
            ))
        return tuple(sig_parts)

class LensSystemOptimizer:
    def __init__(self, matrices):
        self.matrices = matrices
        self.lens_library = []  # Wird dynamisch geladen
        self.vc = ValueConverter()
        self.material = Material
        
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

    def get_beam_parameters(self):
        """Lade Strahlparameter aus der temporären Datei"""
        temp_data_modematcher = config.get_temp_data_modematcher()
        (self.wavelength, self.distance, self.waist_input_sag, self.waist_input_tan, 
        self.waist_position_sag, self.waist_position_tan, self.waist_goal_sag, 
        self.waist_goal_tan, self.waist_position_goal_sag, self.waist_position_goal_tan) = temp_data_modematcher
    
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
    
    '''def fitness_function(self, individual):
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

        return (fitness,)'''
        
    def optimize_lens_system(self, max_lenses, num_runs=100, total_generation=60):
        """Startet die neue Kombinationsoptimierung in einem separaten Thread"""
        self.get_beam_parameters()
        self._load_lens_library_from_temp_file()
        
        try:
            # Validierungen
            if not self.lens_library:
                raise ValueError("No lenses in library. Please select lenses first.")
                
            if len(self.lens_library) < 1:
                raise ValueError("Not enough lenses in library. Need at least 1 lens.")
            
            # Warnung bei vielen Kombinationen - nur für max_lenses berechnen
            n = len(self.lens_library)
            r = max_lenses
            total_combinations = 1
            for i in range(r):
                total_combinations = total_combinations * (n + i) // (i + 1)
            
            if total_combinations > 5000:
                reply = QMessageBox.question(
                    None, 
                    "Large Search Space", 
                    f"This will test {total_combinations} lens combinations with exactly {max_lenses} lenses. This may take a while. Continue?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return None
        
            # Erstelle Thread und Worker-Objekt
            self.thread = QThread()
            self.worker = OptimizationWorker(self, max_lenses, num_runs, total_generation)
            
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