import json
import numpy as np
import config
from deap import base, creator, tools
import random
from os import path
from PyQt5.QtWidgets import QMainWindow, QMessageBox
from PyQt5 import uic
from PyQt5.QtCore import QThread, pyqtSignal, QObject
from PyQt5.QtGui import QPixmap
from src_resonator.problem import Problem
from src_resonator.resonator_types import *
from src_physics.value_converter import ValueConverter
from GUI.optical_plotter import OpticalSystemPlotter
from src_physics.matrices import Matrices
from src_physics.beam import Beam

class Resonator(QObject):
    """
    Main class for resonator optimization now using a Genetic Algorithm (GA).
    """
    setup_generated = pyqtSignal(object)  # Signal für das optische System
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.resonator_window = None
        self.resonator_type = None 
        self.ui_resonator = None
        self.mirror_curvatures = []
        self.vc = ValueConverter()
        self.beam = Beam()
        self.matrices = Matrices()
        self.plotter = None

        # Attributes to store optimization results
        self.l1 = None
        self.l2 = None
        self.l3 = None
        self.lc = None
        self.theta = None
        self.r1_sag = None
        self.r1_tan = None
        self.r2_sag = None
        self.r2_tan = None
        self.selected_class_name = None

    def open_resonator_window(self):
        """
        Creates and shows the resonator configuration window.
        Sets up the UI and connects the necessary signals.
        """
        # Create new window instance without parent
        self.resonator_window = QMainWindow()
        
        # Load the resonator UI
        self.ui_resonator = uic.loadUi(
            path.abspath(path.join(path.dirname(path.dirname(__file__)), 
            "assets/resonator_window.ui")), 
            self.resonator_window
        )
        
        # Set default value for comboBox_problem_class
        self.ui_resonator.comboBox_problem_class.setCurrentText("BowTie")  # oder einen anderen Standardwert
        
        # Configure and show the window
        self.resonator_window.setWindowTitle("Resonator Configuration")
        
        # Connect resonator instance to UI
        self.set_ui_resonator(self.ui_resonator)
        self.temp_file_path = config.get_temp_file_path()

        # Connect resonator window buttons
        self.ui_resonator.button_evaluate_resonator.clicked.connect(
            self.evaluate_resonator)
        self.ui_resonator.button_abort_resonator.clicked.connect(
            self.stop_optimization)

        self.ui_resonator.comboBox_problem_class.currentTextChanged.connect(
            self.config_ui)
        
        self.ui_resonator.button_back.clicked.connect(self.handle_back_button)
        
        self.ui_resonator.pushButton_plot_setup.clicked.connect(self.plot_current_setup)
        
        # Call config_ui explicitly after setting up the UI
        self.config_ui()
        
        # Show the window after configuration
        self.resonator_window.show()

    def plot_current_setup(self):
        """
        Konvertiert das berechnete Resonator-Setup in eine Setup-Liste und sendet es an das Hauptfenster
        """
        # Prüfe ob eine Optimierung durchgeführt wurde
        if not hasattr(self, 'waist_sag') or not hasattr(self, 'l1'):
            QMessageBox.warning(
                self.resonator_window,
                "No Optimization Results",
                "Please run the resonator optimization first before plotting the setup."
            )
            return
        
        try:
            # Hole die gespeicherten Parameter
            wavelength, lc, nc = config.get_temp_light_field_parameters()
            
            # Baue das Setup als Komponenten-Liste auf
            setup_components = []
            
            # 1. Beam-Komponente mit berechneten Waist-Werten
            beam_component = {
                "type": "BEAM",
                "name": "Beam",
                "properties": {
                    "Wavelength": wavelength,
                    "Waist radius sagittal": self.waist_sag,
                    "Waist radius tangential": self.waist_tan,
                    "Waist position sagittal": 0.0,
                    "Waist position tangential": 0.0,
                    "Rayleigh range sagittal": np.pi * self.waist_sag**2 / wavelength,
                    "Rayleigh range tangential": np.pi * self.waist_tan**2 / wavelength,
                    "IS_ROUND": False
                }
            }
            setup_components.append(beam_component)
            
            # 2. NEU: Resonator-spezifische Komponenten basierend auf dem Typ
            if self.selected_class_name == "BowTie":
                # Erstelle eine BowTie-Instanz und setze die berechneten Werte
                bowtie = BowTie()
                bowtie.l1 = self.l1
                bowtie.l2 = self.l2
                bowtie.l3 = self.l3
                bowtie.theta = self.theta
                bowtie.r1_sag = self.r1_sag
                bowtie.r1_tan = self.r1_tan
                bowtie.r2_sag = self.r2_sag
                bowtie.r2_tan = self.r2_tan
                bowtie._add_bowtie_components(setup_components, wavelength, lc, nc)
                
            elif self.selected_class_name == "FabryPerot":
                fabry = FabryPerot()
                fabry.l1 = self.l1
                fabry.r1_sag = self.r1_sag
                fabry.r1_tan = self.r1_tan
                fabry._add_fabryperot_components(setup_components, wavelength, lc, nc)
                
            elif self.selected_class_name == "Rectangle":
                rectangle = Rectangle()
                rectangle.l1 = self.l1
                rectangle.l2 = self.l2
                rectangle.r1_sag = self.r1_sag
                rectangle.r1_tan = self.r1_tan
                rectangle.r2_sag = self.r2_sag
                rectangle.r2_tan = self.r2_tan
                rectangle._add_rectangle_components(setup_components, wavelength, lc, nc)
                
            elif self.selected_class_name == "Triangle":
                triangle = Triangle()
                triangle.l1 = self.l1
                triangle.l2 = self.l2
                triangle.theta = self.theta
                triangle.r1_sag = self.r1_sag
                triangle.r1_tan = self.r1_tan
                triangle.r2_sag = self.r2_sag
                triangle.r2_tan = self.r2_tan
                triangle._add_triangle_components(setup_components, wavelength, lc, nc)
        
            # Übertrage das Setup an das Hauptfenster
            self._transfer_setup_to_mainwindow(setup_components)
            
            QMessageBox.information(
                self.resonator_window,
                "Setup Generated",
                f"Generated {self.selected_class_name} resonator setup with {len(setup_components)} components."
            )
            
        except Exception as e:
            print(f"Error in plot_current_setup: {e}")  # Debug-Ausgabe
            QMessageBox.critical(
                self.resonator_window,
                "Error",
                f"Error generating setup: {str(e)}"
            )

    def _transfer_setup_to_mainwindow(self, setup_components):
        """
        Überträgt das Setup an das Hauptfenster über verschiedene Methoden
        """
        try:
            # Methode 1: Standard Qt-Signal (falls Parent verfügbar)
            parent = self.parent()
            if parent and hasattr(parent, 'receive_setup'):
                parent.receive_setup(setup_components)
                return
            
            # Methode 2: Globale Widget-Suche (Fallback)
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                for widget in app.allWidgets():
                    if hasattr(widget, 'receive_setup') and hasattr(widget, 'setupList'):
                        widget.receive_setup(setup_components)
                        return
            
            # Falls keine Methode funktioniert
            raise Exception("Could not find MainWindow instance to transfer setup")
            
        except Exception as e:
            raise Exception(f"Failed to transfer setup: {e}")

    def close_resonator_window(self):
        """
        Closes the resonator window and resets the reference.
        """
        if self.lib_resonator_window:
            self.ui_select_components_resonator.close()
        if self.parent():
            self.parent().show()
    
    def handle_back_button(self):
        """
        Verbirgt das aktuelle Fenster und zeigt das vorherige Fenster wieder an.
        """
        if hasattr(self, 'previous_window') and self.previous_window:
            self.previous_window.show()
            self.previous_window.raise_()
            # --- NEU: temporäre Komponentenliste leeren ---
            if hasattr(self.previous_window, 'item_selector'):
                self.previous_window.item_selector.temporary_components = []
                self.previous_window.item_selector.update_temporary_list_view()
                # Optional: auch die Anzeige zurücksetzen
                if hasattr(self.previous_window.item_selector, 'update_temporary_list_view'):
                    self.previous_window.item_selector.update_temporary_list_view()
        if self.resonator_window:
            self.resonator_window.hide()
        
    def load_mirror_data(self, filepath):
        """
        Loads mirror data from a JSON file.
        For non-round mirrors (IS_ROUND = 0.0), creates an additional entry 
        with swapped sagittal and tangential curvatures.
        
        Args:
            filepath (str): Path to the JSON file containing mirror definitions
        """
        # Überprüfen, ob die Datei existiert
        if not path.exists(filepath):
            raise FileNotFoundError(f"Die Datei '{filepath}' wurde nicht gefunden.")

        # Laden der JSON-Daten
        with open(filepath, 'r') as file:
            data = json.load(file)

        # Extrahieren der Spiegel-Daten
        self.mirror_curvatures = []
        for component in data.get("components", []):
            if component.get("type") == "MIRROR":
                properties = component.get("properties", {})
                curvature_tangential = properties.get("Radius of curvature tangential", 0.0)
                curvature_sagittal = properties.get("Radius of curvature sagittal", 0.0)
                is_round = properties.get("IS_ROUND", False)
                
                # Normale Variante speichern
                self.mirror_curvatures.append((curvature_sagittal, curvature_tangential, is_round))
                
                # Für nicht-runde Spiegel zusätzlich die getauschte Variante speichern
                if not is_round:
                    self.mirror_curvatures.append((curvature_tangential, curvature_sagittal, is_round))
                    
        # Debugging-Ausgabe
        if not self.mirror_curvatures:
            raise ValueError("Die Liste 'mirror_curvatures' ist leer.")
        
    def config_ui(self):
        self.selected_class_name = self.ui_resonator.comboBox_problem_class.currentText()
        base_path = path.abspath(path.join(path.dirname(__file__), "..", "assets"))
        if self.selected_class_name == "BowTie":
            self.ui_resonator.edit_lower_bound_l1.setDisabled(False)
            self.ui_resonator.edit_upper_bound_l1.setDisabled(False)
            self.ui_resonator.edit_lower_bound_l2.setDisabled(True)
            self.ui_resonator.edit_upper_bound_l2.setDisabled(True)
            self.ui_resonator.edit_lower_bound_l3.setDisabled(False)
            self.ui_resonator.edit_upper_bound_l3.setDisabled(False)
            self.ui_resonator.edit_lower_bound_theta.setDisabled(False)
            self.ui_resonator.edit_upper_bound_theta.setDisabled(False)
            graphic_path = path.join(base_path, "bowtie_layout.png")
            graphic = QPixmap(graphic_path)
            self.ui_resonator.layout_resonator_picture.setMaximumSize(500, 200)
        elif self.selected_class_name == "FabryPerot":
            self.ui_resonator.edit_lower_bound_l1.setDisabled(False)
            self.ui_resonator.edit_upper_bound_l1.setDisabled(False)
            self.ui_resonator.edit_lower_bound_l2.setDisabled(True)
            self.ui_resonator.edit_upper_bound_l2.setDisabled(True)
            self.ui_resonator.edit_lower_bound_l3.setDisabled(True)
            self.ui_resonator.edit_upper_bound_l3.setDisabled(True)
            self.ui_resonator.edit_lower_bound_theta.setDisabled(True)
            self.ui_resonator.edit_upper_bound_theta.setDisabled(True)
            graphic_path = path.join(base_path, "fabryperot_layout.png")
            graphic = QPixmap(graphic_path)
            self.ui_resonator.layout_resonator_picture.setMaximumSize(500, 50)
        elif self.selected_class_name == "Rectangle":
            self.ui_resonator.edit_lower_bound_l1.setDisabled(False)
            self.ui_resonator.edit_upper_bound_l1.setDisabled(False)
            self.ui_resonator.edit_lower_bound_l2.setDisabled(False)
            self.ui_resonator.edit_upper_bound_l2.setDisabled(False)
            self.ui_resonator.edit_lower_bound_l3.setDisabled(True)
            self.ui_resonator.edit_upper_bound_l3.setDisabled(True)
            self.ui_resonator.edit_lower_bound_theta.setDisabled(True)
            self.ui_resonator.edit_upper_bound_theta.setDisabled(True)
            graphic_path = path.join(base_path, "rectangle_layout.png")
            graphic = QPixmap(graphic_path)
            self.ui_resonator.layout_resonator_picture.setMaximumSize(500, 200)
        elif self.selected_class_name == "Triangle":
            self.ui_resonator.edit_lower_bound_l1.setDisabled(False)
            self.ui_resonator.edit_upper_bound_l1.setDisabled(False)
            self.ui_resonator.edit_lower_bound_l2.setDisabled(True)
            self.ui_resonator.edit_upper_bound_l2.setDisabled(True)
            self.ui_resonator.edit_lower_bound_l3.setDisabled(True)
            self.ui_resonator.edit_upper_bound_l3.setDisabled(True)
            self.ui_resonator.edit_lower_bound_theta.setDisabled(False)
            self.ui_resonator.edit_upper_bound_theta.setDisabled(False)
            graphic_path = path.join(base_path, "triangle_layout.png")
            graphic = QPixmap(graphic_path)
            self.ui_resonator.layout_resonator_picture.setMaximumSize(500, 200)
            
        self.ui_resonator.layout_resonator_picture.setPixmap(graphic)
        config.set_temp_resonator_type(self.selected_class_name)

    def set_ui_resonator(self, ui_resonator):
        """Set the ui_resonator reference"""
        self.ui_resonator = ui_resonator

    def get_input(self):
        """
        Retrieves input parameters from the UI and converts them to meters.
        
        Returns:
            numpy.array: Array containing [target_sag, target_tan, nc, lc, n_prop, wavelength]
        """
        self.target_sag = self.vc.convert_to_float(self.ui_resonator.edit_target_waist_sag.text(), self.resonator_window)
        self.target_tan = self.vc.convert_to_float(self.ui_resonator.edit_target_waist_tan.text(), self.resonator_window)
        self.nc = float(self.ui_resonator.edit_crystal_refractive_index.text())
        self.lc = self.vc.convert_to_float(self.ui_resonator.edit_crystal_length.text(), self.resonator_window)
        self.wavelength = self.vc.convert_to_float(self.ui_resonator.edit_wavelength.text(), self.resonator_window)
        self.n_prop = 1
        config.set_temp_light_field_parameters(self.wavelength, self.lc, self.nc)

        return np.array([self.target_sag, self.target_tan, self.nc, self.lc, self.n_prop, self.wavelength])
    
    def getbounds(self):
        """
        Gets geometric bounds from the UI for l1, l3, and theta parameters.
        Converts UI values to appropriate units (meters and radians).
        
        Returns:
            tuple: (l1_min, l1_max, l3_min, l3_max, theta_min, theta_max)
        """
        l1_min = self.vc.convert_to_float(self.ui_resonator.edit_lower_bound_l1.text(), self.resonator_window)
        l1_max = self.vc.convert_to_float(self.ui_resonator.edit_upper_bound_l1.text(), self.resonator_window)
        l2_min = self.vc.convert_to_float(self.ui_resonator.edit_lower_bound_l2.text(), self.resonator_window)
        l2_max = self.vc.convert_to_float(self.ui_resonator.edit_upper_bound_l2.text(), self.resonator_window)
        l3_min = self.vc.convert_to_float(self.ui_resonator.edit_lower_bound_l3.text(), self.resonator_window)
        l3_max = self.vc.convert_to_float(self.ui_resonator.edit_upper_bound_l3.text(), self.resonator_window)
        theta_min = np.deg2rad(float(self.ui_resonator.edit_lower_bound_theta.text())/2)
        theta_max = np.deg2rad(float(self.ui_resonator.edit_upper_bound_theta.text())/2)
    
        return l1_min, l1_max, l2_min, l2_max, l3_min, l3_max, theta_min, theta_max
    
    def get_optimization_parameters(self):
        """
        Holt GA-Parameter aus der UI.
        Benötigt (neu): edit_num_runs, edit_population_number, edit_generation_number,
                        edit_crossover_probability, edit_mutation_probability
        Entfernt (PSO): phi1, phi2, smin, smax
        """
        num_runs = int(float(self.ui_resonator.edit_num_runs.text()))
        population_number = int(float(self.ui_resonator.edit_population_number.text()))
        generation_number = int(float(self.ui_resonator.edit_generation_number.text()))
        crossover_probability = float(self.ui_resonator.edit_crossover_probability.text())
        mutation_probability = float(self.ui_resonator.edit_mutation_probability.text())
        return num_runs, population_number, generation_number, crossover_probability, mutation_probability

    def evaluate_resonator(self):
        """
        Startet GA-Optimierung (ersetzt PSO).
        """
        # FIX: Pfad zur Spiegelauswahl IMMER frisch aus der Config lesen.
        # Frueher wurde self.temp_file_path nur einmal beim Oeffnen des Fensters
        # gesetzt; da das Resonator-Objekt im Mainwindow nur einmal erzeugt und
        # danach wiederverwendet wird, blieb eine spaeter geaenderte Spiegelauswahl
        # unbeachtet (der Matcher rechnete mit den alten Spiegeln weiter, bis das
        # Programm neu gestartet wurde). config.get_temp_file_path() wird von der
        # Spiegelauswahl (select_items.py) bei jeder neuen Auswahl aktualisiert.
        self.temp_file_path = config.get_temp_file_path()
        if self.temp_file_path is None or not path.exists(self.temp_file_path):
            QMessageBox.critical(self.resonator_window, "Error",
                                 "No temporary file found. Please add components and save them.")
            return
        # Runs
        try:
            num_runs = int(self.ui_resonator.edit_num_runs.text())
            if num_runs <= 0:
                raise ValueError
        except ValueError:
            QMessageBox.critical(self.resonator_window, "Error", "Invalid number of runs.")
            return

        # Resonator Typ wählen
        self.selected_class_name = self.ui_resonator.comboBox_problem_class.currentText()
        if self.selected_class_name == "BowTie":
            self.resonator_type = BowTie()
        elif self.selected_class_name == "FabryPerot":
            self.resonator_type = FabryPerot()
        elif self.selected_class_name == "Rectangle":
            self.resonator_type = Rectangle()
        elif self.selected_class_name == "Triangle":
            self.resonator_type = Triangle()
        else:
            QMessageBox.critical(self.resonator_window, "Error", "Invalid resonator type.")
            return

        self.problem = Problem(self.resonator_type)
        selected_file_path = self.temp_file_path
        self.load_mirror_data(selected_file_path)
        if not self.mirror_curvatures:
            QMessageBox.critical(self.resonator_window, "Error",
                                 "The list 'mirror_curvatures' is empty.")
            return

        config.TEMP_FILE_PATH_LIB = self.temp_file_path

        # GA Parameter
        num_runs, population_number, generation_number, cxpb, mutpb = self.get_optimization_parameters()

        # Dimension definieren (wie bisher in PSO)
        self.size = self.problem.problem_dimension()

        # Grenzen laden (für Mutation / Initialisierung)
        self.bounds_cache = self.getbounds()  # (l1_min, l1_max, l2_min, l2_max, l3_min, l3_max, theta_min, theta_max)

        # DEAP Toolbox für GA
        toolbox = base.Toolbox()
        # Individual: bereits in Start mittels creator.Individual definiert
        toolbox.register("individual", self._ga_make_individual)
        toolbox.register("population", tools.initRepeat, list, toolbox.individual)
        toolbox.register("mate", self._ga_crossover)
        toolbox.register("mutate", self._ga_mutation, indpb=0.2)
        toolbox.register("select", tools.selTournament, tournsize=3)
        toolbox.register("evaluate", self.objective)

        population = toolbox.population(n=population_number)

        # Thread starten
        self._aborted = False  # <--- hinzufügen
        self.optimization_thread = GAOptimizationThread(
            self, population, toolbox, generation_number, num_runs,
            cxpb=cxpb, mutpb=mutpb
        )

        total_generations = num_runs * generation_number
        self.ui_resonator.progressBar_build_resonator.setMaximum(total_generations)
        self.ui_resonator.progressBar_build_resonator.setValue(0)
        self.ui_resonator.button_evaluate_resonator.setEnabled(False)
        self.optimization_thread.progress.connect(self.ui_resonator.progressBar_build_resonator.setValue)
        self.optimization_thread.finished.connect(self.optimization_finished)
        self.optimization_thread.start()

    # --- NEU: Abbruch der Optimierung (fehlte -> verursachte AttributeError) ---
    def stop_optimization(self):
        """
        Bricht eine laufende GA-Optimierung ab und reaktiviert den Start-Button.
        """
        if hasattr(self, 'optimization_thread') and self.optimization_thread:
            try:
                if self.optimization_thread.isRunning():
                    self._aborted = True
                    self.optimization_thread.stop()
                    self.optimization_thread.wait(300)
            except Exception:
                pass
        if self.ui_resonator and hasattr(self.ui_resonator, 'button_evaluate_resonator'):
            self.ui_resonator.button_evaluate_resonator.setEnabled(True)

    # --- NEU: Callback nach Abschluss / Abbruch ---
    def optimization_finished(self, best_individual):
        """
        Übernimmt das beste Individuum, berechnet Waists erneut und aktualisiert UI.
        """
        # Button wieder aktivieren
        if self.ui_resonator and hasattr(self.ui_resonator, 'button_evaluate_resonator'):
            self.ui_resonator.button_evaluate_resonator.setEnabled(True)

        # Bei Abbruch keine Auswertung
        if getattr(self, "_aborted", False):
            return

        if best_individual is None:
            QMessageBox.information(self.resonator_window, "Finished", "No valid solution found.")
            return

        # Gene entpacken je nach Resonator-Typ
        if self.selected_class_name == "BowTie":
            l1, l3, theta, m1, m2 = best_individual
            self.l1, self.l3, self.theta = l1, l3, theta
            self.l2 = ((2 * l1) + self.lc + l3) / (2 * np.cos(2*theta))
        elif self.selected_class_name == "FabryPerot":
            l1, m1 = best_individual
            self.l1, self.l3, self.theta = l1, None, 0.0
            self.l2 = None
            m2 = m1
        elif self.selected_class_name == "Rectangle":
            l1, l2, m1, m2 = best_individual
            self.l1, self.l2, self.l3, self.theta = l1, l2, None, np.pi/4
        elif self.selected_class_name == "Triangle":
            l1, theta, m1, m2 = best_individual
            self.l1, self.theta = l1, theta
            self.l2 = (l1 + self.lc / 2)/np.cos(2 * theta)
            self.l3 = None

        # Spiegel-Indizes begrenzen
        m1 = int(np.clip(m1, 0, len(self.mirror_curvatures)-1))
        m2 = int(np.clip(m2, 0, len(self.mirror_curvatures)-1))
        r1_sag, r1_tan = self.mirror_curvatures[m1][:2]
        r2_sag, r2_tan = self.mirror_curvatures[m2][:2]
        self.r1_sag, self.r1_tan, self.r2_sag, self.r2_tan = r1_sag, r1_tan, r2_sag, r2_tan

        # Waists berechnen (gleiche Logik wie in objective)
        if self.selected_class_name == "BowTie":
            roundtrip_matrix_sag = self.problem.roundtrip_sagittal(self.nc, self.lc, self.n_prop, self.l1, self.l3, r1_sag, r2_sag, self.theta)
            roundtrip_matrix_tan = self.problem.roundtrip_tangential(self.nc, self.lc, self.n_prop, self.l1, self.l3, r1_tan, r2_tan, self.theta)
        elif self.selected_class_name == "FabryPerot":
            roundtrip_matrix_sag = self.problem.roundtrip_sagittal(self.nc, self.lc, self.n_prop, self.l1, r1_sag)
            roundtrip_matrix_tan = self.problem.roundtrip_tangential(self.nc, self.lc, self.n_prop, self.l1, r1_tan)
        elif self.selected_class_name == "Rectangle":
            roundtrip_matrix_sag = self.problem.roundtrip_sagittal(self.nc, self.lc, self.n_prop, self.l1, self.l2, r1_sag, r2_sag)
            roundtrip_matrix_tan = self.problem.roundtrip_tangential(self.nc, self.lc, self.n_prop, self.l1, self.l2, r1_tan, r2_tan)
        elif self.selected_class_name == "Triangle":
            roundtrip_matrix_sag = self.problem.roundtrip_sagittal(self.nc, self.lc, self.n_prop, self.l1, r1_sag, r2_sag, self.theta)
            roundtrip_matrix_tan = self.problem.roundtrip_tangential(self.nc, self.lc, self.n_prop, self.l1, r1_tan, r2_tan, self.theta)

        m_sag = abs((roundtrip_matrix_sag[0, 0] + roundtrip_matrix_sag[1, 1]) / 2)
        m_tan = abs((roundtrip_matrix_tan[0, 0] + roundtrip_matrix_tan[1, 1]) / 2)
        b_sag = abs(roundtrip_matrix_sag[0, 1])
        b_tan = abs(roundtrip_matrix_tan[0, 1])

        if 1 - m_sag**2 < 0:
            self.waist_sag = 1e6
        else:
            self.waist_sag = np.sqrt(((b_sag * self.wavelength) / np.pi) *
                                     (np.sqrt(abs(1 / (1 - m_sag**2)))))
        if 1 - m_tan**2 < 0:
            self.waist_tan = 1e6
        else:
            self.waist_tan = np.sqrt(((b_tan * self.wavelength) / np.pi) *
                                     (np.sqrt(abs(1 / (1 - m_tan**2)))))

        if self.ui_resonator:
            try:
                if hasattr(self.ui_resonator, 'label_fitness'):
                    self.ui_resonator.label_fitness.setText(f"{best_individual.fitness.values[0]:.3e}")
                if hasattr(self.ui_resonator, 'label_waist'):
                    self.ui_resonator.label_waist.setText(f"{self.vc.convert_to_nearest_string(self.waist_sag)} / {self.vc.convert_to_nearest_string(self.waist_tan)}")
                # Optional: Geometrie-Parameter anzeigen (falls Labels vorhanden)
                if hasattr(self.ui_resonator, 'label_length1') and self.l1 is not None:
                    self.ui_resonator.label_length1.setText(f"{self.vc.convert_to_nearest_string(self.l1)}")
                if hasattr(self.ui_resonator, 'label_length2') and self.l2 is not None:
                    self.ui_resonator.label_length2.setText(f"{self.vc.convert_to_nearest_string(self.l2)}")
                if hasattr(self.ui_resonator, 'label_length3') and self.l3 is not None:
                    # FIX: zeigte vorher faelschlich l1 an
                    self.ui_resonator.label_length3.setText(f"{self.vc.convert_to_nearest_string(self.l3)}")
                if hasattr(self.ui_resonator, 'label_theta') and self.theta is not None:
                    self.ui_resonator.label_theta.setText(f"{np.rad2deg(2*self.theta):.2f}°")
                if hasattr(self.ui_resonator, 'label_mirror1'):
                    self.ui_resonator.label_mirror1.setText(f"{self.vc.convert_to_nearest_string(self.r1_sag)} / {self.vc.convert_to_nearest_string(self.r1_tan)}")
                if hasattr(self.ui_resonator, 'label_mirror2'):
                    self.ui_resonator.label_mirror2.setText(f"{self.vc.convert_to_nearest_string(self.r2_sag)} / {self.vc.convert_to_nearest_string(self.r2_tan)}")
                if hasattr(self.ui_resonator, 'label_stability'):
                    self.ui_resonator.label_stability.setText(f"{m_sag:.3f} / {m_tan:.3f}")
                if hasattr(self.resonator_window, 'statusBar'):
                    self.resonator_window.statusBar().showMessage("Optimization finished", 5000)
            except Exception:
                pass

    # --- GA Hilfsfunktionen ---

    def _ga_make_individual(self):
        """
        Erzeugt ein GA-Individual entsprechend des gewählten Resonatortyps.
        Reihenfolge der Gene:
          BowTie:      [l1, l3, theta, mirror1, mirror2]
          FabryPerot:  [l1, mirror1]
          Rectangle:   [l1, l2, mirror1, mirror2]
          Triangle:    [l1, theta, mirror1, mirror2]
        """
        l1_min, l1_max, l2_min, l2_max, l3_min, l3_max, th_min, th_max = self.bounds_cache
        mc_len = len(self.mirror_curvatures)
        if self.selected_class_name == "BowTie":
            data = [
                random.uniform(l1_min, l1_max),
                random.uniform(l3_min, l3_max),
                random.uniform(th_min, th_max),
                random.randrange(mc_len),
                random.randrange(mc_len)
            ]
        elif self.selected_class_name == "FabryPerot":
            data = [
                random.uniform(l1_min, l1_max),
                random.randrange(mc_len)
            ]
        elif self.selected_class_name == "Rectangle":
            data = [
                random.uniform(l1_min, l1_max),
                random.uniform(l2_min, l2_max),
                random.randrange(mc_len),
                random.randrange(mc_len)
            ]
        elif self.selected_class_name == "Triangle":
            data = [
                random.uniform(l1_min, l1_max),
                random.uniform(th_min, th_max),
                random.randrange(mc_len),
                random.randrange(mc_len)
            ]
        ind = creator.Individual(data)
        return ind

    def _ga_crossover(self, ind1, ind2):
        """
        Custom Crossover: für kontinuierliche Parameter arithmetisch (Mittel),
        für diskrete Spiegelindizes zufälliger Elternwert.
        """
        # Welche Indizes sind kontinuierlich?
        if self.selected_class_name == "BowTie":
            cont_idx = [0, 1, 2]
        elif self.selected_class_name == "FabryPerot":
            cont_idx = [0]
        elif self.selected_class_name == "Rectangle":
            cont_idx = [0, 1]
        elif self.selected_class_name == "Triangle":
            cont_idx = [0, 1]
        else:
            cont_idx = []

        for i in range(len(ind1)):
            if i in cont_idx:
                if random.random() < 0.5:
                    # arithmetischer Mix
                    a = 0.5
                    v1 = ind1[i]
                    v2 = ind2[i]
                    ind1[i] = a * v1 + (1 - a) * v2
                    ind2[i] = a * v2 + (1 - a) * v1
            else:
                # diskret: swap mit 50%
                if random.random() < 0.5:
                    ind1[i], ind2[i] = ind2[i], ind1[i]
        return ind1, ind2

    def _ga_mutation(self, individual, indpb=0.2):
        """
        Mutation: mit Wahrscheinlichkeit indpb Parameter ersetzen (Re-Initialization).
        Für diskrete Spiegel -> neuer Index; für kontinuierliche -> uniform in Bounds.
        """
        l1_min, l1_max, l2_min, l2_max, l3_min, l3_max, th_min, th_max = self.bounds_cache
        mc_len = len(self.mirror_curvatures)
        for i in range(len(individual)):
            if random.random() < indpb:
                if self.selected_class_name == "BowTie":
                    if i == 0:
                        individual[i] = random.uniform(l1_min, l1_max)
                    elif i == 1:
                        individual[i] = random.uniform(l3_min, l3_max)
                    elif i == 2:
                        individual[i] = random.uniform(th_min, th_max)
                    else:
                        individual[i] = random.randrange(mc_len)
                elif self.selected_class_name == "FabryPerot":
                    if i == 0:
                        individual[i] = random.uniform(l1_min, l1_max)
                    else:
                        individual[i] = random.randrange(mc_len)
                elif self.selected_class_name == "Rectangle":
                    if i == 0:
                        individual[i] = random.uniform(l1_min, l1_max)
                    elif i == 1:
                        individual[i] = random.uniform(l2_min, l2_max)
                    else:
                        individual[i] = random.randrange(mc_len)
                elif self.selected_class_name == "Triangle":
                    if i == 0:
                        individual[i] = random.uniform(l1_min, l1_max)
                    elif i == 1:
                        individual[i] = random.uniform(th_min, th_max)
                    else:
                        individual[i] = random.randrange(mc_len)
        return (individual,)

    def objective(self, individual):
        """
        Fitness-Funktion (unverändert, nur PSO-Text entfernt).
        """
        # ...unveränderter Inhalt deiner bisherigen objective() Funktion...
        # (Belasse deinen bestehenden Code hier – nur Docstring angepasst)
        if self.selected_class_name == "BowTie":
            l1, l3, theta, mirror1, mirror2 = individual
        elif self.selected_class_name == "FabryPerot":
            l1, mirror1 = individual
            l3, theta, mirror2 = 0, 0, 0
        elif self.selected_class_name == "Rectangle":
            l1, l2, mirror1, mirror2 = individual
            l3, theta = 0, np.pi / 4
        elif self.selected_class_name == "Triangle":
            l1, theta, mirror1, mirror2 = individual
            l3 = 0
        # ... Rest identisch ...
        # (Behalte deinen bisherigen Code zur Fitnessberechnung komplett bei)
        # --- BEGIN aus vorhandenem Code ---
        mirror1 = int(np.clip(mirror1, 0, len(self.mirror_curvatures) - 1))
        mirror2 = int(np.clip(mirror2, 0, len(self.mirror_curvatures) - 1))
        r1_sag, r1_tan = self.mirror_curvatures[mirror1][:2]
        r2_sag, r2_tan = self.mirror_curvatures[mirror2][:2]
        if self.selected_class_name == "BowTie":
            roundtrip_matrix_sag = self.problem.roundtrip_sagittal(self.nc, self.lc, self.n_prop, l1, l3, r1_sag, r2_sag, theta)
            roundtrip_matrix_tan = self.problem.roundtrip_tangential(self.nc, self.lc, self.n_prop, l1, l3, r1_tan, r2_tan, theta)
        elif self.selected_class_name == "FabryPerot":
            roundtrip_matrix_sag = self.problem.roundtrip_sagittal(self.nc, self.lc, self.n_prop, l1, r1_sag)
            roundtrip_matrix_tan = self.problem.roundtrip_tangential(self.nc, self.lc, self.n_prop, l1, r1_tan)
        elif self.selected_class_name == "Rectangle":
            roundtrip_matrix_sag = self.problem.roundtrip_sagittal(self.nc, self.lc, self.n_prop, l1, l2, r1_sag, r2_sag)
            roundtrip_matrix_tan = self.problem.roundtrip_tangential(self.nc, self.lc, self.n_prop, l1, l2, r1_tan, r2_tan)
        elif self.selected_class_name == "Triangle":
            roundtrip_matrix_sag = self.problem.roundtrip_sagittal(self.nc, self.lc, self.n_prop, l1, r1_sag, r2_sag, theta)
            roundtrip_matrix_tan = self.problem.roundtrip_tangential(self.nc, self.lc, self.n_prop, l1, r1_tan, r2_tan, theta)
        m_sag = np.abs((roundtrip_matrix_sag[0, 0] + roundtrip_matrix_sag[1, 1]) / 2)
        m_tan = np.abs((roundtrip_matrix_tan[0, 0] + roundtrip_matrix_tan[1, 1]) / 2)
        b_sag = np.abs(roundtrip_matrix_sag[0, 1])
        b_tan = np.abs(roundtrip_matrix_tan[0, 1])
        if 1 - m_sag**2 <= 0:
            waist_sag = 1e6
        else:
            waist_sag = np.sqrt(((b_sag * self.wavelength) / (np.pi)) *
                                (np.sqrt(np.abs(1 / (1 - m_sag**2)))))
        if 1 - m_tan**2 <= 0:
            waist_tan = 1e6
        else:
            waist_tan = np.sqrt(((b_tan * self.wavelength) / (np.pi)) *
                                (np.sqrt(np.abs(1 / (1 - m_tan**2)))))
        if abs(m_sag) > 1 or abs(m_tan) > 1:
            return (1e6,)
        fitness_value, = self.problem.fitness(waist_sag, waist_tan,
                                              self.target_sag, self.target_tan)
        return (fitness_value,)
        # --- END vorhandener Code ---

    # Entfernte PSO-spezifische Methoden:
    # - generate()
    # - update_particle()
    # (nicht mehr benötigt)

    def close_window(self):
        try:
            self.stop_optimization()
        except Exception:
            pass
        try:
            if hasattr(self, "resonator_window") and self.resonator_window:
                self.resonator_window.close()
        except Exception:
            pass

class GAOptimizationThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(object)

    def __init__(self, resonator, population, toolbox, generation_count, num_runs, cxpb, mutpb):
        super().__init__()
        self.resonator = resonator
        self.population = population
        self.toolbox = toolbox
        self.generation_count = generation_count
        self.num_runs = num_runs
        self.cxpb = cxpb
        self.mutpb = mutpb
        self.abort_flag = False
        self.best_overall = None
        # Input-Werte sichern
        inputs = self.resonator.get_input()
        self.target_sag, self.target_tan, self.nc, self.lc, self.n_prop, self.wavelength = inputs

    def run(self):
        current_progress = 0
        for run in range(self.num_runs):
            if self.abort_flag:
                break
            # Neue Population pro Run
            pop = [self.toolbox.clone(ind) if hasattr(self.toolbox, 'clone') else creator.Individual(ind) for ind in self.population]
            # Initial evaluieren
            for ind in pop:
                ind.fitness.values = self.toolbox.evaluate(ind)

            # Bester
            best = tools.selBest(pop, 1)[0]

            for gen in range(self.generation_count):
                if self.abort_flag:
                    break
                offspring = self.toolbox.select(pop, len(pop))
                offspring = list(map(lambda x: creator.Individual(x[:]), offspring))

                # Crossover
                for i in range(0, len(offspring)-1, 2):
                    if random.random() < self.cxpb:
                        self.toolbox.mate(offspring[i], offspring[i+1])
                        del offspring[i].fitness.values, offspring[i+1].fitness.values

                # Mutation
                for ind in offspring:
                    if random.random() < self.mutpb:
                        self.toolbox.mutate(ind)
                        if hasattr(ind, 'fitness') and ind.fitness.valid:
                            del ind.fitness.values

                # Re-evaluate
                for ind in offspring:
                    if not ind.fitness.valid:
                        ind.fitness.values = self.toolbox.evaluate(ind)

                # Ersatz (generational)
                pop = offspring

                # Best updaten
                gen_best = tools.selBest(pop, 1)[0]
                if gen_best.fitness.values[0] < best.fitness.values[0]:
                    best = gen_best

                current_progress += 1
                self.progress.emit(current_progress)

            if (self.best_overall is None or
                best.fitness.values[0] < self.best_overall.fitness.values[0]):
                self.best_overall = creator.Individual(best[:])
                self.best_overall.fitness.values = best.fitness.values

        self.finished.emit(self.best_overall)

    def stop(self):
        self.abort_flag = True