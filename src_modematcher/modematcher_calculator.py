from PyQt5.QtWidgets import QMainWindow, QMessageBox
from PyQt5 import uic
from os import path
from src_modematcher.lens_system_optimizier import LensSystemOptimizer
import config
from PyQt5.QtWidgets import QMessageBox

class ModematcherCalculationWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.item_selector = None  # Reference to ItemSelector
        self.modematcher_calculation = None  # Reference to Modematcher calculation

    def closeEvent(self, event):
        """
        Called when the window is about to be closed (X button).
        """
        event.ignore()  # Prevent default closing
        if self.item_selector:
            self.item_selector.handle_back_button()

class ModematcherCalculator:
    def __init__(self, modematcher):
        self.modematcher = modematcher
        self.previous_window = None  # NEU: Referenz zum vorherigen Fenster
        
        # Optimizer initialisieren (ohne feste Linsenbibliothek)
        from src_physics.matrices import Matrices
        self.matrices = Matrices()
        self.optimizer = LensSystemOptimizer(self.matrices)

    def set_previous_window(self, previous_window):
        """
        Setze das vorherige Fenster für Navigation
        """
        self.previous_window = previous_window

    def show_with_previous(self, previous_window):
        """
        Zeige Calculator-Fenster mit Referenz zum vorherigen Fenster
        """
        self.previous_window = previous_window
        self.open_modematcher_calculator_window()

    def open_modematcher_calculator_window(self):
        """UI-Integration"""
        self.modematcher_calculation_window = QMainWindow()
        # Load the modematcher UI
        self.ui_modematcher_calculation = uic.loadUi(
            path.abspath(path.join(path.dirname(path.dirname(__file__)), 
            "assets/modematcher_calculation_window.ui")), 
            self.modematcher_calculation_window
        )
        
        # Configure and show the window
        self.modematcher_calculation_window.setWindowTitle("Mode Matching")
        self.modematcher_calculation_window.show()
        
        # Button-Verbindungen
        self.ui_modematcher_calculation.button_optimize.clicked.connect(self.run_optimization)
        self.ui_modematcher_calculation.button_stop_optimization.clicked.connect(self.stop_optimization)
        # NEU: Back-Button verbinden
        self.ui_modematcher_calculation.button_back.clicked.connect(self.handle_back_button)
    
        
        # Optional: Lens-Selection Button falls vorhanden
        if hasattr(self.ui_modematcher_calculation, 'button_select_lenses'):
            self.ui_modematcher_calculation.button_select_lenses.clicked.connect(self.open_lens_selection)
    
    def handle_back_button(self):
        """
        Schließt das aktuelle Fenster und zeigt das vorherige (Parameter-Fenster) an
        """
        try:
            # Aktuelles Fenster schließen
            if hasattr(self, 'modematcher_calculation_window') and self.modematcher_calculation_window:
                self.modematcher_calculation_window.close()
                self.modematcher_calculation_window = None
                self.ui_modematcher_calculation = None
            
            # Vorheriges Fenster anzeigen
            if hasattr(self, 'previous_window') and self.previous_window:
                self.previous_window.show()
                self.previous_window.raise_()  # Fenster in den Vordergrund bringen
                self.previous_window.activateWindow()  # Fenster aktivieren
            else:
                # Fallback: Erstelle neues Parameter-Fenster
                if hasattr(self.modematcher, 'open_modematcher_parameter_window'):
                    self.modematcher.open_modematcher_parameter_window()
                    
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error in handle_back_button: {e}")
            # Fallback: Versuche Parameter-Fenster zu öffnen
            try:
                if hasattr(self.modematcher, 'open_modematcher_parameter_window'):
                    self.modematcher.open_modematcher_parameter_window()
            except Exception as fallback_error:
                QMessageBox.critical(None, "Error", f"Fallback error: {fallback_error}")
    
    def close_modematcher_calculation_window(self):
        """
        Alternative Methode zum Schließen (für Rückwärtskompatibilität)
        """
        self.handle_back_button()
    
    def open_lens_selection(self):
        """Öffne Linsenauswahl-Dialog"""
        try:
            # Setze Context für Linsenauswahl
            if hasattr(self.parent(), 'current_context'):
                self.parent().current_context = "modematcher"
            
            # Öffne ItemSelector für Linsenauswahl
            from src_libraries.select_items import ItemSelector
            self.lens_selector = ItemSelector(self.parent())
            self.lens_selector.open_library_window(self.parent())
            
        except Exception as e:
            QMessageBox.critical(
                self.modematcher_calculation_window,
                "Error",
                f"Error opening lens selection: {str(e)}"
            )
    
    def run_optimization(self):
        """GUI-Callback für Optimierung - ohne Parameter-Eingabe"""
        # Prüfe ob Linsen ausgewählt wurden
        if not self.optimizer.lens_library:
            QMessageBox.warning(
                self.modematcher_calculation_window,
                "No Lenses Selected",
                "Please select lenses first using the 'Select Lenses' button.")
            return

        # Übergebe UI-Referenz an den Optimizer
        self.optimizer.ui_modematcher_calculation = self.ui_modematcher_calculation

        # Starte Optimierung mit der aktuellen Anzahl an Linsen
        self.optimizer.optimize_lens_system(
            max_lenses=self.ui_modematcher_calculation.lensNumber.value())

    def stop_optimization(self):
        """Stoppe die Optimierung"""
        try:
            self.optimizer.stop_optimization()
        except Exception as e:
            QMessageBox.critical(self, "Error", "Error stopping optimization: " + str(e))

    def calculate_optimal_system(self):
        """Berechne optimales Linsensystem mit geladenen Parametern"""
        try:
            # Prüfe ob Linsenbibliothek verfügbar ist
            if not self.optimizer.lens_library:
                raise Exception("No lens library available. Please select lenses first.")
            
            max_lenses=self.ui_modematcher_calculation.lensNumber.value()
            # Verwende die Parameter aus get_beam_parameters (keine UI-Parameter mehr nötig)
            optimized_system = self.optimizer.optimize_lens_system(max_lenses=max_lenses)
            
            return optimized_system
            
        except Exception as e:
            QMessageBox.critical(self, "Error", "Error during optimization: " + str(e))
            return None

