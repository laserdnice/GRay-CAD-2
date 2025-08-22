from PyQt5.QtWidgets import QMainWindow, QMessageBox, QApplication
from PyQt5 import uic
from os import path
from src_modematcher.lens_system_optimizier import LensSystemOptimizer
from src_physics.matrices import Matrices
import config
from PyQt5.QtWidgets import QMessageBox

class ModematcherCalculationWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.item_selector = None  # Reference to ItemSelector
        self.modematcher_calculation = None  # Reference to Modematcher calculation

    def closeEvent(self, event):
        """
        X-Button: Preview-Setup entfernen und vorheriges Fenster zeigen (wie handle_back_button).
        """
        try:
            # Preview im MainWindow entfernen (falls aktiv)
            app = QApplication.instance()
            if app:
                for w in app.allWidgets():
                    if hasattr(w, 'remove_preview_setup'):
                        try:
                            w.remove_preview_setup()
                        except Exception:
                            pass
                        break

            # Vorheriges Fenster anzeigen
            if self.previous_window:
                self.previous_window.show()
                self.previous_window.raise_()
                self.previous_window.activateWindow()
            elif hasattr(self.parent(), 'open_modematcher_parameter_window'):
                try:
                    self.parent().open_modematcher_parameter_window()
                except Exception:
                    pass
        finally:
            event.accept()

class ModematcherCalculator:
    def __init__(self, modematcher):
        self.modematcher = modematcher
        self.previous_window = None  # NEU: Referenz zum vorherigen Fenster
        self.last_optimization_results = [] 
        self._selected_results = set()
        self.current_worker = None
        
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
        # Verwende die spezialisierte Window-Klasse, damit closeEvent greift
        self.modematcher_calculation_window = ModematcherCalculationWindow()
        self.modematcher_calculation_window.previous_window = self.previous_window

        self.ui_modematcher_calculation = uic.loadUi(
            path.abspath(path.join(path.dirname(path.dirname(__file__)),
                                   "assets/modematcher_calculation_window.ui")),
            self.modematcher_calculation_window
        )

        self.modematcher_calculation_window.setWindowTitle("Mode Matching")
        self.modematcher_calculation_window.show()

        # Button-Verbindungen
        self.ui_modematcher_calculation.button_optimize.clicked.connect(self.run_optimization)
        self.ui_modematcher_calculation.button_stop_optimization.clicked.connect(self.stop_optimization)
        self.ui_modematcher_calculation.button_back.clicked.connect(self.handle_back_button)

        if hasattr(self.ui_modematcher_calculation, 'button_select_lenses'):
            self.ui_modematcher_calculation.button_select_lenses.clicked.connect(self.open_lens_selection)
        if hasattr(self.ui_modematcher_calculation, 'button_create_setup'):
            self.ui_modematcher_calculation.button_create_setup.clicked.connect(self.create_selected_setups)
    
    def handle_back_button(self):
        """
        Schließt das aktuelle Fenster und zeigt das vorherige (Parameter-Fenster) an.
        Entfernt dabei das Preview-Setup aus dem Hauptfenster (falls vorhanden).
        """
        try:
            # Preview im MainWindow entfernen (falls aktiv)
            app = QApplication.instance()
            if app:
                for w in app.allWidgets():
                    if hasattr(w, 'remove_preview_setup'):
                        try:
                            w.remove_preview_setup()
                        except Exception:
                            pass
                        break

            # Aktuelles Fenster schließen
            if hasattr(self, 'modematcher_calculation_window') and self.modematcher_calculation_window:
                self.modematcher_calculation_window.close()
                self.modematcher_calculation_window = None
                self.ui_modematcher_calculation = None
            
            # Vorheriges Fenster anzeigen
            if hasattr(self, 'previous_window') and self.previous_window:
                self.previous_window.show()
                self.previous_window.raise_()
                self.previous_window.activateWindow()
            else:
                if hasattr(self.modematcher, 'open_modematcher_parameter_window'):
                    self.modematcher.open_modematcher_parameter_window()
                    
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error in handle_back_button: {e}")
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
        """GUI-Callback für Optimierung"""
        # Prüfe ob Linsen ausgewählt wurden
        if not self.optimizer.lens_library:
            QMessageBox.warning(
                self.modematcher_calculation_window,
                "No Lenses Selected",
                "Please select lenses first using the 'Select Lenses' button.")
            return

        try:
            max_lenses = self.ui_modematcher_calculation.lensNumber.value()
            
            # Starte Optimierung und erhalte Worker
            self.current_worker = self.optimizer.optimize_lens_system(max_lenses=max_lenses)
            
            # Verbinde Worker-Signale mit UI-Callbacks
            self.current_worker.finished.connect(self._on_optimization_finished)
            self.current_worker.error.connect(self._on_optimization_error)
            self.current_worker.finished.connect(self._reset_ui)
            
            # Setup Progress Bar
            self._setup_progress_ui()
            
        except Exception as e:
            QMessageBox.critical(
                self.modematcher_calculation_window,
                "Optimization Error", 
                f"Error setting up optimization: {str(e)}"
            )

    def _setup_progress_ui(self):
        """Setup Progress Bar und verbinde Signale"""
        if hasattr(self.ui_modematcher_calculation, 'progressBar'):
            # Progress Bar für Prozent (0-100)
            self.ui_modematcher_calculation.progressBar.setMinimum(0)
            self.ui_modematcher_calculation.progressBar.setMaximum(100)
            self.ui_modematcher_calculation.progressBar.setValue(0)
            
            # Verbinde Worker-Fortschritt
            if self.current_worker:
                self.current_worker.progress.connect(self.ui_modematcher_calculation.progressBar.setValue)
            
            # Deaktiviere Optimize-Button
            if hasattr(self.ui_modematcher_calculation, 'button_optimize'):
                self.ui_modematcher_calculation.button_optimize.setEnabled(False)
        else:
            # Fallback zu QProgressDialog
            from PyQt5.QtWidgets import QProgressDialog
            self.progress_dialog = QProgressDialog("Running optimization...", "Cancel", 0, 100)
            self.progress_dialog.setWindowTitle("Optimization Progress")
            self.progress_dialog.setMinimumDuration(0)
            self.progress_dialog.setValue(0)
            self.progress_dialog.setModal(True)
            
            if self.current_worker:
                self.progress_dialog.canceled.connect(self.current_worker.stop)
                self.current_worker.progress.connect(self.progress_dialog.setValue)
                self.current_worker.finished.connect(self.progress_dialog.close)
                self.current_worker.error.connect(self.progress_dialog.close)
            
            self.progress_dialog.show()

    def stop_optimization(self):
        """Stoppe die Optimierung"""
        try:
            if self.current_worker:
                self.current_worker.stop()
            self.optimizer.stop_optimization()
            self._reset_ui()
        except Exception as e:
            QMessageBox.critical(
                self.modematcher_calculation_window, 
                "Error", 
                f"Error stopping optimization: {str(e)}"
            )
            
    def _on_optimization_error(self, error_message):
        """Wird aufgerufen, wenn ein Fehler während der Optimierung auftritt"""
        QMessageBox.critical(
            self.modematcher_calculation_window, 
            "Optimization Error", 
            error_message
        )
        # UI zurücksetzen
        self._reset_ui()

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
    
    def create_selected_setups(self):
        """Delegate an Optimizer: persist selected optimization results as setups."""
        try:
            self.optimizer.create_selected_setups()
        except Exception as e:
            QMessageBox.critical(self.modematcher_calculation_window, "Error", f"Error creating setups: {e}")

    def create_selected_setups(self):
        """Erstellt persistente Setups für ausgewählte Ergebnisse"""
        try:
            selected = self.get_selected_results()
            if not selected:
                QMessageBox.information(
                    self.modematcher_calculation_window, 
                    "Create Setups", 
                    "No results selected."
                )
                return
                
            for idx, res in enumerate(selected, start=1):
                comps = self._build_setup_components_from_result(res)
                fit = res.get('fitness', 0.0)
                name = f"OptResult {idx} (fit {fit:.2e})"
                self._transfer_setup_to_mainwindow(comps, setup_name=name)
                
            QMessageBox.information(
                self.modematcher_calculation_window, 
                "Create Setups", 
                f"Created {len(selected)} setup(s)."
            )
        except Exception as e:
            QMessageBox.critical(
                self.modematcher_calculation_window, 
                "Error", 
                f"Error creating setups: {e}"
            )

    def _on_optimization_finished(self, results):
        """
        Befüllt das QTableWidget tableResults mit allen Optimierungsergebnissen.
        Zeigt jetzt sagittale UND tangentiale Werte (zweizeilig pro Zelle).
        Klick auf eine Zeile erzeugt eine temporäre Plot-Vorschau dieses Setups.
        """
        if not results:
            QMessageBox.warning(
                self.modematcher_calculation_window, 
                "Optimization Result", 
                "No valid solution found in any run."
            )
            return

        self.last_optimization_results = results  # Speichern für Preview
        self._selected_results = set()  # Reset selection

        # Hole Zielwerte
        self.optimizer.get_beam_parameters()
        w0_sag_goal = self.optimizer.waist_goal_sag
        w0_tan_goal = self.optimizer.waist_goal_tan
        z0_sag_goal = self.optimizer.distance + self.optimizer.waist_position_goal_sag
        z0_tan_goal = self.optimizer.distance + self.optimizer.waist_position_goal_tan

        if hasattr(self.ui_modematcher_calculation, 'tableResults'):
            table = self.ui_modematcher_calculation.tableResults
            table.clearSelection()
            table.setSortingEnabled(False)  # Temporär aus beim Füllen
            table.setRowCount(len(results))
            table.setColumnCount(7)

            def fmt(v): 
                return self.optimizer.vc.convert_to_nearest_string(v)

            from src_modematcher.lens_system_optimizier import NumericTableWidgetItem
            from PyQt5.QtWidgets import QCheckBox
            from PyQt5.QtCore import Qt

            RESULT_ROLE = Qt.UserRole + 99

            for row, result in enumerate(results):
                waist_sag = result['waist_sag']
                waist_tan = result.get('waist_tan', float('nan'))
                position_sag = result['position_sag']
                position_tan = result.get('position_tan', float('nan'))
                fitness = result['fitness']
                lens_count = len(result['lenses'])

                delta_w0_sag = waist_sag - w0_sag_goal
                delta_w0_tan = waist_tan - w0_tan_goal
                delta_z0_sag = position_sag - z0_sag_goal
                delta_z0_tan = position_tan - z0_tan_goal

                item_fitness = NumericTableWidgetItem(f"{fitness:.3e}", fitness)
                item_fitness.setData(RESULT_ROLE, result)
                item_lenses = NumericTableWidgetItem(f"{lens_count}", lens_count)
                item_waist = NumericTableWidgetItem(f"{fmt(waist_sag)}\n{fmt(waist_tan)}", waist_sag)
                item_delta_waist = NumericTableWidgetItem(f"{fmt(delta_w0_sag)}\n{fmt(delta_w0_tan)}", abs(delta_w0_sag))
                item_position = NumericTableWidgetItem(f"{fmt(position_sag)}\n{fmt(position_tan)}", position_sag)
                item_delta_position = NumericTableWidgetItem(f"{fmt(delta_z0_sag)}\n{fmt(delta_z0_tan)}", abs(delta_z0_sag))

                item_waist.setToolTip(f"Sagittal: {waist_sag:.6g}\nTangential: {waist_tan:.6g}")
                item_delta_waist.setToolTip(f"ΔSag: {delta_w0_sag:.6g}\nΔTan: {delta_w0_tan:.6g}")
                item_position.setToolTip(f"Sagittal focus pos: {position_sag:.6g}\nTangential focus pos: {position_tan:.6g}")
                item_delta_position.setToolTip(f"ΔSag pos: {delta_z0_sag:.6g}\nΔTan pos: {delta_z0_tan:.6g}")

                table.setItem(row, 0, item_fitness)
                table.setItem(row, 1, item_lenses)
                table.setItem(row, 2, item_waist)
                table.setItem(row, 3, item_delta_waist)
                table.setItem(row, 4, item_position)
                table.setItem(row, 5, item_delta_position)

                # Checkbox-Spalte
                from PyQt5.QtWidgets import QTableWidgetItem
                checkbox_item = QTableWidgetItem("")  # Platzhalter für Sortierung
                checkbox_item.setFlags(Qt.ItemIsEnabled)  # Nicht auswählbar/editierbar
                table.setItem(row, 6, checkbox_item)
                cb = QCheckBox()
                cb.stateChanged.connect(
                    lambda state, chk=cb, res=result: self._on_result_checkbox_changed(state, chk, res)
                )
                table.setCellWidget(row, 6, cb)

            table.setSortingEnabled(True)
            table.sortItems(0, Qt.AscendingOrder)

            # Spaltenbreiten an Header anpassen
            header = table.horizontalHeader()
            for col in range(table.columnCount()):
                # Mindestbreite ist Header-Text plus Padding
                header_text = table.horizontalHeaderItem(col).text() if table.horizontalHeaderItem(col) else ""
                font_metrics = table.fontMetrics()
                header_width = font_metrics.boundingRect(header_text).width() + 20
                
                # Aktuelle Breite der Spalte (nach Inhalt)
                table.resizeColumnToContents(col)
                content_width = table.columnWidth(col)
                
                # Setze Breite auf das Maximum von Header-Breite und Inhaltsbreite
                table.setColumnWidth(col, max(header_width, content_width))
            
            # Spezialfall: Checkbox-Spalte (feste Breite)
            if table.columnCount() > 6:
                table.setColumnWidth(6, 60)

            if not getattr(table, "_preview_connected", False):
                table.itemSelectionChanged.connect(self._on_table_selection_changed)
                table._preview_connected = True

    def _reset_ui(self):
        """Setzt UI-Elemente nach der Optimierung zurück"""
        if hasattr(self.ui_modematcher_calculation, 'progressBar'):
            self.ui_modematcher_calculation.progressBar.setValue(0)
            
        if hasattr(self.ui_modematcher_calculation, 'button_optimize'):
            self.ui_modematcher_calculation.button_optimize.setEnabled(True)
            
    def _on_result_checkbox_changed(self, state, checkbox, result):
        """Verwaltet Auswahl-Liste für angehakte Resultate"""
        from PyQt5.QtCore import Qt
        
        if state == Qt.Checked:
            self._selected_results.add(id(result))
        else:
            self._selected_results.discard(id(result))
            
    def get_selected_results(self):
        """Gibt die ausgewählten Result-Dicts zurück"""
        selected = []
        for r in self.last_optimization_results:
            if id(r) in self._selected_results:
                selected.append(r)
        return selected
    
    def _on_table_selection_changed(self):
        """Handler: Auswahl im Ergebnis-Table -> dazugehöriges Setup temporär plotten"""
        try:
            table = self.ui_modematcher_calculation.tableResults
            selected_ranges = table.selectedRanges()
            if not selected_ranges:
                return
            
            row = selected_ranges[0].topRow()
            first_item = table.item(row, 0)
            if first_item is None:
                return
                
            from PyQt5.QtCore import Qt
            RESULT_ROLE = Qt.UserRole + 99
            result = first_item.data(RESULT_ROLE)
            if result:
                self._preview_result(result)
        except Exception:
            pass

    def _preview_result(self, result):
        """Erzeugt temporäres Setup für Preview"""
        try:
            self.optimizer.get_beam_parameters()
            setup_components = self._build_setup_components_from_result(result)
            self._transfer_preview_setup_to_mainwindow(setup_components)
        except Exception as e:
            QMessageBox.critical(
                self.modematcher_calculation_window, 
                "Preview Error", 
                f"Failed to preview setup: {str(e)}"
            )
            
    def _build_setup_components_from_result(self, result):
        """Baut Komponentenliste aus Optimierungsergebnis"""
        import numpy as np
        
        # Hole aktuelle Beam-Parameter
        wavelength = self.optimizer.wavelength
        waist_sag = self.optimizer.waist_input_sag
        waist_tan = self.optimizer.waist_input_tan
        waist_pos_sag = self.optimizer.waist_position_sag
        waist_pos_tan = self.optimizer.waist_position_tan
        
        components = [{
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
        }]
        
        sorted_lenses = sorted(result.get('lenses', []), key=lambda x: x[1])
        last_position = 0.0
        
        for lens, position in sorted_lenses:
            distance = position - last_position
            if distance > 0:
                components.append({
                    "type": "PROPAGATION",
                    "name": f"Propagation {last_position:.3f}m to {position:.3f}m",
                    "properties": {
                        "Length": distance,
                        "Refractive index": 1.0
                    }
                })
            components.append(dict(lens))
            last_position = position
        
        final_distance = self.optimizer.distance - last_position
        if final_distance > 0:
            components.append({
                "type": "PROPAGATION",
                "name": f"Propagation {last_position:.3f}m to {self.optimizer.distance:.3f}m",
                "properties": {
                    "Length": final_distance,
                    "Refractive index": 1.0
                }
            })
        return components
    
    def _transfer_preview_setup_to_mainwindow(self, setup_components):
        """
        Sendet ein temporäres Setup (Preview) an das Hauptfenster ohne es zu speichern.
        """
        try:
            app = QApplication.instance()
            if app:
                for widget in app.allWidgets():
                    if hasattr(widget, 'receive_preview_setup') and hasattr(widget, 'setupList'):
                        widget.receive_preview_setup(setup_components)
                        return
            raise Exception("Could not find MainWindow instance for preview transfer")
        except Exception as e:
            QMessageBox.critical(
                self.modematcher_calculation_window, 
                "Preview Error", 
                f"Failed to transfer preview setup: {e}"
            )
            
    def _transfer_setup_to_mainwindow(self, setup_components, setup_name=None):
        """
        Überträgt ein (persistentes) Setup an das Hauptfenster.
        Optional mit explizitem Namen (falls MainWindow diese Variante unterstützt).
        """
        try:
            app = QApplication.instance()
            if app:
                for widget in app.allWidgets():
                    if setup_name and hasattr(widget, 'receive_setup_with_name') and hasattr(widget, 'setupList'):
                        widget.receive_setup_with_name(setup_components, setup_name)
                        return
                    if hasattr(widget, 'receive_setup') and hasattr(widget, 'setupList'):
                        widget.receive_setup(setup_components)
                        return
            raise Exception("Could not find MainWindow instance to transfer setup")
        except Exception as e:
            raise Exception(f"Failed to transfer setup: {e}")