#Python 3.10.2
# -*- coding: utf-8 -*-
"""
@author: Jens Gumm, TU Darmstadt, LQO-Group
Main window implementation for the GRay-CAD application.
Handles the primary UI and window management.
"""

# PyQt5 imports for GUI components
from PyQt5 import uic
from pyqtgraph import *
from os import path
from PyQt5.QtCore import QThread, QObject, pyqtSignal, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMainWindow, QMessageBox
import json
import pyqtgraph as pg
import numpy as np
import copy, traceback

# Custom module imports
from src_resonator.resonators import Resonator
from src_libraries.libraries import Libraries
from src_libraries.select_items import ItemSelector
from src_modematcher.modematcher_parameters import ModematcherParameters
from src_physics.beam import Beam
from src_physics.matrices import Matrices
from src_physics.value_converter import ValueConverter
from GUI.actions import Action
from GUI.setupList import SetupList
from GUI.componentList import ComponentList
from GUI.errorHandler import CustomMessageBox
from src_physics.material import Material
from GUI.optical_plotter import OpticalSystemPlotter
from GUI.properties_handler import PropertiesHandler

class PlotWorker(QObject):
    finished = pyqtSignal(tuple)  # (z_data, w_data)

    def __init__(self, beam, wavelength, q_value, optical_system, n=1):
        super().__init__()
        self.beam = beam
        self.wavelength = wavelength
        self.q_value = q_value
        self.optical_system = optical_system
        self.n = n

    def run(self):
        z_data, w_data, z_setup = self.beam.propagate_through_system(
            self.wavelength, self.q_value, self.optical_system, n=self.n
        )
        self.finished.emit((z_data, w_data, z_setup))

class MainWindow(QMainWindow, PropertiesHandler):
    """
    Main application window class.
    """
    
    def __init__(self, *args, **kwargs):
        """
        Initialize the main window and set up the UI components.
        Creates instances of Resonator and Matrices classes.
        Sets up menu actions and button connections.
        """
        QMainWindow.__init__(self, *args, **kwargs)
        PropertiesHandler.__init__(self, live_plot_callback=self.update_live_plot)
        
        if hasattr(self, '_property_update_timer') and hasattr(self, 'update_rayleigh'):
            self._property_update_timer.timeout.connect(self.update_rayleigh)
            
        # Timer vor allen Verbindungen initialisieren
        self._live_plot_update_timer = QtCore.QTimer(self)
        self._live_plot_update_timer.setSingleShot(True)
        self._live_plot_update_timer.setInterval(10)
        self._live_plot_update_timer.timeout.connect(self.update_live_plot)

        # Create instances of helper classes
        self.res = Resonator(parent=self)
        self.beam = Beam()
        self.modematcher = ModematcherParameters(self)
        self.lib = Libraries(self)
        self.item_selector_modematcher = ItemSelector(self)
        self.item_selector_res = ItemSelector(self)
        self.matrices = Matrices()
        self.vc = ValueConverter()
        self.action = Action()
        self.material = Material
        
        self.vlines = []
        self.curves = []
        self.z_setup = 0
        
        self._plot_busy = False

        # Variable, um den Kontext zu speichern
        self.current_context = None
        self.wavelength = None  # Default wavelength
        self._last_component_item = None

        # Signal verbinden
        self.res.setup_generated.connect(self.receive_setup)
        
        # Set application window icon
        self.setWindowIcon(QIcon(path.abspath(path.join(path.dirname(__file__), 
                         "../../assets/TaskbarIcon.png"))))

        # Load the main UI from .ui file
        self.ui = uic.loadUi(path.abspath(path.join(path.dirname(__file__), "../assets/mainwindow.ui")), self)

        # NEU: Jetzt erst OpticalSystemPlotter initialisieren (nach UI-Laden)
        self.optical_plotter = OpticalSystemPlotter(self.plotWidget, self.beam, self.matrices, self.vc)

        # Connect menu items to their respective handlers
        self.ui.action_Open.triggered.connect(lambda: self.action.action_open(self))
        self.ui.action_Save.triggered.connect(lambda: self.action.action_save(self))
        self.ui.action_Save_as.triggered.connect(lambda: self.action.action_save_as(self))
        self.ui.action_Exit.triggered.connect(lambda: self.action.action_exit(self))
        self.ui.action_Tips_and_tricks.triggered.connect(lambda: self.action.action_tips_and_tricks(self))
        self.ui.action_About.triggered.connect(lambda: self.action.action_about(self))
        self.ui.action_Save.setShortcut(QtGui.QKeySequence.Save)
        self.ui.action_Save_as.setShortcut(QtGui.QKeySequence.SaveAs)
        self.ui.action_Open.setShortcut(QtGui.QKeySequence.Open)

        # Connect library menu item to the library window
        self.ui.action_Library.triggered.connect(self.lib.open_library_window)
        
        # Plot from resonator setup
        self.res.setup_generated.connect(self.receive_setup)
        
        # Connect buttons to their respective handlers
        self.ui.action_Cavity_Designer.triggered.connect(lambda: self.action.handle_build_resonator(self))
        self.ui.action_Modematcher.triggered.connect(lambda: self.action.handle_modematcher(self))

        # Library and component list setup
        old_component_list = self.findChild(QtWidgets.QListWidget, "componentList")
        old_setup_list = self.findChild(QtWidgets.QListWidget, "setupList")

        self.componentList = ComponentList(self)
        self.componentList.setObjectName("componentList")
        self.setupList = SetupList(self)
        self.setupList.setObjectName("setupList")

        # Im Layout ersetzen
        parent1 = old_component_list.parent()
        parent2 = old_setup_list.parent()
        layout1 = parent1.layout()
        layout2 = parent2.layout()
        layout1.replaceWidget(old_component_list, self.componentList)
        layout2.replaceWidget(old_setup_list, self.setupList)
        old_component_list.deleteLater()
        old_setup_list.deleteLater()

        self.setups = []
        # Initiales Setup als "Setup 0" speichern
        setup0 = []
        for i in range(self.setupList.count()):
            item = self.setupList.item(i)
            comp = item.data(QtCore.Qt.UserRole)
            setup0.append(copy.deepcopy(comp))
        self.setups.append({"name": "Setup 0", "components": setup0})
        self.ui.comboBoxSetup.clear()
        self.ui.comboBoxSetup.addItem("Setup 0")

        self.load_library_list_from_folder("Library")
        self.componentList.itemClicked.connect(self.on_component_clicked)
        self.setupList.itemClicked.connect(self.on_component_clicked)
        self.libraryList.itemClicked.connect(self.on_library_selected)

        # Buttons and Dropdown for new setup
        self.ui.pushButton_create_setup.clicked.connect(self.create_new_setup)
        self.ui.comboBoxSetup.currentIndexChanged.connect(self.on_setup_selection_changed)
        self.ui.comboBoxSetup.editTextChanged.connect(self.on_setup_name_edited)
        self.ui.pushButton_delete_setup.clicked.connect(self.delete_setup)

        # Connect buttons in the setupTree
        self.ui.buttonDeleteItem.clicked.connect(lambda: self.action.delete_selected_setup_item(self))
        self.ui.buttonMoveUp.clicked.connect(lambda: self.action.move_selected_setup_item_up(self))
        self.ui.buttonMoveDown.clicked.connect(lambda: self.action.move_selected_setup_item_down(self))
        self.ui.buttonAddComponent.clicked.connect(lambda: self.action.move_selected_component_to_setupList(self))
        self.ui.buttonScaleToSetup.clicked.connect(lambda: self.optical_plotter.scale_visible_setup())

        self.cursor_vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('k', width=1, style=Qt.DashLine))
        self.plotWidget.addItem(self.cursor_vline, ignoreBounds=True)
        self.cursor_vline.setZValue(100)
        self.update_live_plot()
        
        # Live update for the optical system plot
        #self.setupList.itemChanged.connect(lambda _: self.update_live_plot_delayed())
        self.setupList.model().rowsInserted.connect(lambda *_: self.update_live_plot_delayed())
        self.setupList.model().rowsRemoved.connect(lambda *_: self.update_live_plot_delayed())
        self.setupList.model().modelReset.connect(lambda *_: self.update_live_plot_delayed())
        self.setupList.model().rowsMoved.connect(lambda *args: self.update_live_plot_delayed())
        
        if "Variable parameter" in self._property_fields:
            self._property_fields["Variable parameter"].currentIndexChanged.connect(self.update_design_focal_length_fields)
        
        self.cursor_vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('k', width=1, style=Qt.DashLine))
        self.plotWidget.addItem(self.cursor_vline, ignoreBounds=True)
        self.cursor_vline.setZValue(100)  # Damit sie immer oben liegt

        def mouseMoved(evt):
            pos = evt
            if self.plotWidget.sceneBoundingRect().contains(pos):
                mousePoint = self.plotWidget.getViewBox().mapSceneToView(pos)
                z = mousePoint.x()
                self.cursor_vline.setPos(z)
                idx = np.searchsorted(self.optical_plotter.z_data, z)
                if idx == 0:
                    z_val = self.optical_plotter.z_data[0]
                    w_sag_val = self.optical_plotter.w_sag_data[0]
                    w_tan_val = self.optical_plotter.w_tan_data[0]
                elif idx == len(self.optical_plotter.z_data):
                    z_val = self.optical_plotter.z_data[-1]
                    w_sag_val = self.optical_plotter.w_sag_data[-1]
                    w_tan_val = self.optical_plotter.w_tan_data[-1]
                else:
                    # Interpolation zwischen idx-1 und idx
                    z0, z1 = self.optical_plotter.z_data[idx-1], self.optical_plotter.z_data[idx]
                    w0_sag, w1_sag = self.optical_plotter.w_sag_data[idx-1], self.optical_plotter.w_sag_data[idx]
                    w0_tan, w1_tan = self.optical_plotter.w_tan_data[idx-1], self.optical_plotter.w_tan_data[idx]
                    t = (z - z0) / (z1 - z0) if z1 != z0 else 0
                    z_val = z
                    w_sag_val = w0_sag + t * (w1_sag - w0_sag)
                    w_tan_val = w0_tan + t * (w1_tan - w0_tan)
                # Vermeide Neubau des optischen Systems für jede Mausbewegung – nutze Segment-Caches
                if self.wavelength is None:
                    # einmalig Wellenlänge aus Beam holen
                    for i in range(self.setupList.count()):
                        comp_item = self.setupList.item(i)
                        comp = comp_item.data(QtCore.Qt.UserRole)
                        if isinstance(comp, dict) and comp.get("type", "").upper() == "BEAM":
                            self.wavelength = comp.get("properties", {}).get("Wavelength", 514e-9)
                            break
                # q direkt aus Cache (schnell)
                q_at_sag = self.optical_plotter.get_q_at(z_val, mode="sagittal") if hasattr(self, 'optical_plotter') else None
                q_at_tan = self.optical_plotter.get_q_at(z_val, mode="tangential") if hasattr(self, 'optical_plotter') else None
                self.ui.label_z_position.setText(f"{self.vc.convert_to_nearest_string(z_val, self)}")
                self.ui.label_w_sag.setText(f"{self.vc.convert_to_nearest_string(w_sag_val, self)}")
                self.ui.label_w_tan.setText(f"{self.vc.convert_to_nearest_string(w_tan_val, self)}")
                # Radius of Curvature direkt aus q (ohne erneute System-Propagation)
                if q_at_sag is not None and np.real(q_at_sag) != 0:
                    roc_sag = (abs(q_at_sag)**2) / np.real(q_at_sag)
                    self.ui.label_roc_sag.setText(f"{self.vc.convert_to_nearest_string(roc_sag, self)}")
                if q_at_tan is not None and np.real(q_at_tan) != 0:
                    roc_tan = (abs(q_at_tan)**2) / np.real(q_at_tan)
                    self.ui.label_roc_tan.setText(f"{self.vc.convert_to_nearest_string(roc_tan, self)}")
        # Connect signal to function
        self.plotWidget.scene().sigMouseMoved.connect(mouseMoved)
        self.plotWidget.getViewBox().sigXRangeChanged.connect(self.optical_plotter.update_plot_for_visible_range)
        self.plotWidget.hideButtons()

        # Action-Instanz erstellen
        self.action_handler = Action()
    
        # Default-Setup-Datei erstellen falls nicht vorhanden
        self.action_handler.create_default_setup_file()
    
        # Projects-Ordner in Fenstertitel anzeigen
        self.setWindowTitle(f"GRay-CAD 2 - Projects: {self.action_handler.projects_dir}")
        
        self._previous_setup_index = 0  # Initial ist Setup 0 aktiv
    
    def update_live_plot_delayed_original(self):
        """Original-Implementation für Live-Plot-Updates"""
        if hasattr(self, '_live_plot_update_timer'):
            self._live_plot_update_timer.stop()
            self._live_plot_update_timer.start()

    def mark_as_modified(self):
        self.has_unsaved_changes = True
        title = self.windowTitle()
        if not title.endswith("*"):
            self.setWindowTitle(title + "*")
            
    def mark_as_saved(self):
        self.has_unsaved_changes = False
        title = self.windowTitle()
        if title.endswith("*"):
            self.setWindowTitle(title[:-1])

    def create_new_setup(self):
        # WICHTIG: Speichere das aktuelle Setup vor dem Erstellen eines neuen
        self.save_current_setup()
        
        # Finde die höchste existierende Setup-Nummer aus self.setups
        existing_numbers = []
        for setup in self.setups:
            name = setup.get("name", "")
            if name.startswith("Setup "):
                try:
                    num = int(name.split("Setup ")[1])
                    existing_numbers.append(num)
                except (ValueError, IndexError):
                    pass

        # Bestimme die nächste verfügbare Nummer
        if existing_numbers:
            next_number = max(existing_numbers) + 1
        else:
            next_number = 1

        # Erstelle neues Setup mit der höchsten Nummer
        new_setup_name = f"Setup {next_number}"

        # Verwende das Default-Setup aus SetupList statt das aktuelle Setup
        default_components = SetupList.get_default_components()
        new_setup = [copy.deepcopy(comp) for comp in default_components]
        
        # Verwende den berechneten Namen statt "new setup {count}"
        self.setups.append({"name": new_setup_name, "components": new_setup})
        self.update_setup_names_and_combobox()
        self.ui.comboBoxSetup.setCurrentIndex(len(self.setups) - 1)

    def update_setup_names_and_combobox(self):
        self.ui.comboBoxSetup.blockSignals(True)
        self.ui.comboBoxSetup.clear()
        for setup in self.setups:
            self.ui.comboBoxSetup.addItem(setup.get("name", "Setup"))
        self.ui.comboBoxSetup.blockSignals(False)
    
    def on_setup_name_edited(self, new_name):
        idx = self.ui.comboBoxSetup.currentIndex()
        if 0 <= idx < len(self.setups):
            self.setups[idx]["name"] = new_name
            # Optional: ComboBox-Eintrag aktualisieren (falls nötig)
            self.ui.comboBoxSetup.setItemText(idx, new_name)

    def save_current_setup(self, target_index=None):
        """Speichert die aktuelle setupList in das angegebene Setup (nicht während Preview)."""
        if getattr(self, '_preview_active', False):
            return  # Preview nicht persistieren
        
        if target_index is None:
            target_index = self.ui.comboBoxSetup.currentIndex()
        
        if target_index < 0 or target_index >= len(self.setups):
            return
            
        if self.setupList.count() == 0:
            return
            
        current_setup = []
        for i in range(self.setupList.count()):
            item = self.setupList.item(i)
            comp = item.data(QtCore.Qt.UserRole)
            if comp:
                current_setup.append(copy.deepcopy(comp))
    
        self.setups[target_index]["components"] = current_setup

    def on_setup_selection_changed(self, index):
        """Wechselt zwischen Setups mit vollständiger Isolation (bricht Preview ab)."""
        # Beende ggf. Preview vor Wechsel
        if getattr(self, '_preview_active', False):
            self.cancel_temporary_setup()
        
        if index < 0 or index >= len(self.setups):
            return
    
        self._switching_setups = True
    
        try:
            # Speichere das VORHERIGE Setup (falls vorhanden)
            previous_index = getattr(self, '_previous_setup_index', None)
            if previous_index is not None and previous_index != index:
                self.save_current_setup(previous_index)
        
            self._previous_setup_index = index
        
            # Trenne alle Signal-Verbindungen UND leere Property-Panel
            if hasattr(self, '_property_fields'):
                for field in self._property_fields.values():
                    if hasattr(field, 'blockSignals'):
                        field.blockSignals(True)
                
                    if hasattr(field, 'textChanged'):
                        try:
                            field.textChanged.disconnect()
                        except TypeError:
                            pass
                    if hasattr(field, 'stateChanged'):
                        try:
                            field.stateChanged.disconnect()
                        except TypeError:
                            pass
                    if hasattr(field, 'currentIndexChanged'):
                        try:
                            field.currentIndexChanged.disconnect()
                        except TypeError:
                            pass
            
                self._property_fields.clear()
        
            # Leere das Property-Panel komplett
            if hasattr(self, 'propertyLayout'):
                while self.propertyLayout.count():
                    child = self.propertyLayout.takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
        
            self._last_component_item = None
            self.setupList.clear()
        
            # Lade das neue Setup
            setup = self.setups[index]["components"]
            for comp in setup:
                item = QtWidgets.QListWidgetItem(comp.get("name", "Unnamed"))
                item.setData(QtCore.Qt.UserRole, copy.deepcopy(comp))
                self.setupList.addItem(item)
        
            self.update_live_plot()
            self.scale_visible_setup()
    
        finally:
            self._switching_setups = False

    def delete_setup(self):
        idx = self.ui.comboBoxSetup.currentIndex()
        if idx < 0 or idx >= len(self.setups):
            return
        # Optional: Das erste Setup darf nicht gelöscht werden
        if len(self.setups) == 1:
            QtWidgets.QMessageBox.warning(self, "Warnung", "At least one setup must be maintained.")
            return
        # Setup entfernen
        del self.setups[idx]
        self.update_setup_names_and_combobox()
        # Index anpassen: vorheriges oder erstes Setup auswählen
        if idx >= len(self.setups):
            idx = len(self.setups) - 1
        self.ui.comboBoxSetup.setCurrentIndex(idx)

    def closeEvent(self, event):
        try:
            self.setupList.model().modelReset.disconnect()
            self.setupList.itemChanged.disconnect()
            self.setupList.model().rowsInserted.disconnect()
            self.setupList.model().rowsRemoved.disconnect()
        except Exception:
            pass
        super().closeEvent(event)
    
    def on_component_clicked(self, item):
        """Handle clicks on components in the setup list."""
        clicked_component = item.data(QtCore.Qt.UserRole)
        
        # Verhindere mehrfache Verarbeitung desselben Items
        if hasattr(self, "_last_component_item") and self._last_component_item == item:
            return
        
        # Speichere Properties der vorherigen Komponente
        if hasattr(self, "_last_component_item") and self._last_component_item is not None:
            try:
                last_component = self._last_component_item.data(QtCore.Qt.UserRole)
                if isinstance(last_component, dict):
                    updated_last = self.save_properties_to_component(last_component)
                    if updated_last:
                        self._last_component_item.setData(QtCore.Qt.UserRole, updated_last)
            except (RuntimeError, AttributeError):
                pass
    
        # Setze das neue Item
        self._last_component_item = item

        # Lade die neue Komponente
        if not isinstance(clicked_component, dict):
            return
        
        # Zeige die neue Komponente an
        self.labelType.setText(clicked_component.get("type", ""))
        self.labelName.setText(clicked_component.get("name", ""))
        self.labelManufacturer.setText(clicked_component.get("manufacturer", ""))
        
        # Lade Properties der neuen Komponente
        props = clicked_component.get("properties", {})

        # Dynamisch Properties hinzufügen für Linsen
        ctype = clicked_component.get("type", "").strip().upper()
        if ctype in ["LENS"]:
            # WICHTIG: Prüfe und setze "Variable parameter" falls es fehlt
            if "Variable parameter" not in props:
                props["Variable parameter"] = "Edit focal length"
            if "Plan lens" not in props:
                props["Plan lens"] = False
            if "Lens material" not in props:
                props["Lens material"] = "NBK7"
            
            # Aktualisiere die Komponente mit den neuen Properties
            clicked_component["properties"] = props
            item.setData(QtCore.Qt.UserRole, clicked_component)

        # Zeige Properties an
        self.show_properties(props, clicked_component)
        
        # 6. Setze das neue Item als letztes Item
        self._last_component_item = item
        
    def load_library_list_from_folder(self, folder_path):
        self.libraryList.clear()
        for filename in os.listdir(folder_path):
            if filename.endswith(".json"):
                lib_name = filename[:-5]  # Entfernt ".json"
                self.libraryList.addItem(lib_name)
    
    def on_library_selected(self, item):
        # Name der Bibliothek aus dem Listeneintrag
        lib_name = item.text()
        # Lade die entsprechende JSON-Datei
        lib_path = path.join("Library", lib_name + ".json")
        try:
            with open(lib_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            components = data.get("components", [])
            self.componentList.clear()
            for comp in components:
                name = comp.get("name", "Unnamed")
                list_item = QtWidgets.QListWidgetItem(name)
                list_item.setData(QtCore.Qt.UserRole, comp)
                self.componentList.addItem(list_item)
        except Exception as e:
            self.componentList.clear()
            QtWidgets.QMessageBox.critical(self, "Error", f"Library could not be loaded:\n{e}")

    def build_optical_system_from_setup_list(self, mode="sagittal"):
        """
        Builds the optical system from the components in setupList.
        Returns a list of (matrix_function, parameters).
        """
        optical_system = []
        for i in range(self.setupList.count()):
            item = self.setupList.item(i)
            component = item.data(QtCore.Qt.UserRole)
            if not isinstance(component, dict):
                continue
            ctype = component.get("type", "").strip().upper()
            props = component.get("properties", {})

            if ctype == "BEAM" and component.get("name", "").strip().lower() == "beam":
                self.wavelength = props.get("Wavelength", 514e-9)
                continue
            
            elif ctype == "PROPAGATION":
                length = props.get("Length", 0.1)
                n = props.get("Refractive index", 1.0)
                optical_system.append((self.matrices.free_space, (length, n)))
                
            elif ctype == "LENS":
                material = props.get("Lens material", "NBK7")
                lambda_design = props.get("Design wavelength", 514e-9)
                n_design = self.material.get_n(material, lambda_design)
                n = self.material.get_n(material, self.wavelength)
                is_plane = self._to_bool(props.get("Plan lens", False))
                is_round = props.get("IS_ROUND", False)
                
                if mode == "sagittal":
                    f_design = props.get("Focal length sagittal")
                    r_in = props.get("Radius of curvature sagittal")
                else:
                    f_design = props.get("Focal length tangential")
                    r_in = props.get("Radius of curvature tangential")
                
                if is_plane:
                    r_out = 1e100
                else:
                    r_out = - r_in

                if props.get("Variable parameter") == "Edit both curvatures":
                    f_actual = ((n_design-1)/(n-1)) * ((n_design-1) * ((1/r_in) - (1/r_out)))**(-1)
                    f_design_calculated = ((n_design-1) * ((1/r_in) - (1/r_out)))**(-1)
                    
                    if mode == "sagittal":
                        props["Focal length sagittal"] = f_design_calculated
                        if is_round:  # Nur bei sphärischer Linse beide Werte aktualisieren
                            props["Focal length tangential"] = f_design_calculated
                    else:  # mode == "tangential"
                        props["Focal length tangential"] = f_design_calculated
                        if is_round:  # Nur bei sphärischer Linse beide Werte aktualisieren
                            props["Focal length sagittal"] = f_design_calculated
                    
                    # Aktualisiere die Komponente in der Liste
                    component["properties"] = props
                    item.setData(QtCore.Qt.UserRole, component)
                    
                    # Aktualisiere die UI-Felder falls diese Linse gerade angezeigt wird
                    if hasattr(self, "_last_component_item") and self._last_component_item == item:
                        if "Focal length sagittal" in self._property_fields and (mode == "sagittal" or is_round):
                            self._property_fields["Focal length sagittal"].blockSignals(True)
                            self._property_fields["Focal length sagittal"].setText(
                                self.vc.convert_to_nearest_string(f_design_calculated)
                            )
                            self._property_fields["Focal length sagittal"].blockSignals(False)
                        
                        if "Focal length tangential" in self._property_fields and (mode == "tangential" or is_round):
                            self._property_fields["Focal length tangential"].blockSignals(True)
                            self._property_fields["Focal length tangential"].setText(
                                self.vc.convert_to_nearest_string(f_design_calculated)
                            )
                            self._property_fields["Focal length tangential"].blockSignals(False)
                    
                else:
                    f_actual = ((n_design-1)/(n-1)) * f_design
                    if is_plane:
                        r_in_calculated = ((n_design - 1)**2)/(n - 1) * f_actual
                    else:
                        r_in_calculated = 2*((n_design - 1)**2)/(n - 1) * f_actual
                    
                    # Aktualisiere nur entsprechend is_round und mode
                    if mode == "sagittal":
                        props["Radius of curvature sagittal"] = r_in_calculated
                        if is_round:  # Nur bei sphärischer Linse beide Werte aktualisieren
                            props["Radius of curvature tangential"] = r_in_calculated
                    else:  # mode == "tangential"
                        props["Radius of curvature tangential"] = r_in_calculated
                        if is_round:  # Nur bei sphärischer Linse beide Werte aktualisieren
                            props["Radius of curvature sagittal"] = r_in_calculated
                    
                    # Aktualisiere die Komponente in der Liste
                    component["properties"] = props
                    item.setData(QtCore.Qt.UserRole, component)
                    
                    # Aktualisiere die UI-Felder falls diese Linse gerade angezeigt wird
                    if hasattr(self, "_last_component_item") and self._last_component_item == item:
                        if "Radius of curvature sagittal" in self._property_fields and (mode == "sagittal" or is_round):
                            self._property_fields["Radius of curvature sagittal"].blockSignals(True)
                            self._property_fields["Radius of curvature sagittal"].setText(
                                self.vc.convert_to_nearest_string(r_in_calculated)
                            )
                            self._property_fields["Radius of curvature sagittal"].blockSignals(False)
                        
                        if "Radius of curvature tangential" in self._property_fields and (mode == "tangential" or is_round):
                            self._property_fields["Radius of curvature tangential"].blockSignals(True)
                            self._property_fields["Radius of curvature tangential"].setText(
                                self.vc.convert_to_nearest_string(r_in_calculated)
                            )
                            self._property_fields["Radius of curvature tangential"].blockSignals(False)
                    
                optical_system.append((self.matrices.lens, (f_actual,)))
                
            elif ctype == "MIRROR":
                if mode == "sagittal":
                    r = props.get("Radius of curvature sagittal")
                    theta = props.get("Angle of incidence")
                    optical_system.append((self.matrices.curved_mirror_sagittal, (r, theta,)))
                else:
                    r = props.get("Radius of curvature tangential")
                    theta = props.get("Angle of incidence")
                    optical_system.append((self.matrices.curved_mirror_tangential, (r, theta,)))
                    
            elif ctype == "ABCD":
                if mode == "sagittal":
                    A = props.get("A sagittal")
                    B = props.get("B sagittal")
                    C = props.get("C sagittal")
                    D = props.get("D sagittal")
                    optical_system.append((self.matrices.ABCD, (A, B, C, D, )))
                else:
                    A = props.get("A tangential")
                    B = props.get("B tangential")
                    C = props.get("C tangential")
                    D = props.get("D tangential")
                    optical_system.append((self.matrices.ABCD, (A, B, C, D, )))
                    
            elif ctype == "THICK LENS":
                n_in = 1  # Default
                if i > 0:
                    for j in range(i - 1, -1, -1):
                        prev_item = self.setupList.item(j)
                        prev_component = prev_item.data(QtCore.Qt.UserRole)
                        if prev_component.get("type", "").strip().upper() == "PROPAGATION":
                            n_in = prev_component.get("properties", {}).get("Refractive index", 1)
                            break

                # Suche n_out (nächste Propagation oder Medium)
                n_out = 1  # Default
                if i < self.setupList.count() - 1:
                    for j in range(i + 1, self.setupList.count()):
                        next_item = self.setupList.item(j)
                        next_component = next_item.data(QtCore.Qt.UserRole)
                        if next_component.get("type", "").strip().upper() == "PROPAGATION":
                            n_out = next_component.get("properties", {}).get("Refractive index", 1)
                            break
                material = props.get("Lens material")
                n_lens = self.material.get_n(material, self.wavelength)
                thickness = props.get("Thickness", 0.01)
                if mode == "sagittal":
                    r_in_sag = props.get("Input radius of curvature sagittal", 0.1)
                    r_out_sag = props.get("Output radius of curvature sagittal", 0.1)
                    optical_system.append((self.matrices.refraction_curved_interface, (r_in_sag, n_in, n_lens)))
                    optical_system.append((self.matrices.free_space, (thickness, n_lens)))
                    optical_system.append((self.matrices.refraction_curved_interface, (-r_out_sag, n_lens, n_out)))
                else:
                    r_in_tan = props.get("Input radius of curvature tangential", 0.1)
                    r_out_tan = props.get("Output radius of curvature tangential", 0.1)
                    optical_system.append((self.matrices.refraction_curved_interface, (r_in_tan, n_in, n_lens)))
                    optical_system.append((self.matrices.free_space, (thickness, n_lens)))
                    optical_system.append((self.matrices.refraction_curved_interface, (-r_out_tan, n_lens, n_out)))

            # ... weitere Typen ...
        return optical_system
        
    def plot_optical_system(self, z_start_sag, z_start_tan, wavelength, waist_sag, waist_tan, n, optical_system_sag, optical_system_tan):
        self.optical_plotter.plot_optical_system(z_start_sag, z_start_tan, wavelength, waist_sag, waist_tan, n, optical_system_sag, optical_system_tan)

    def update_plot_for_visible_range(self, *args, **kwargs):
        self.optical_plotter.update_plot_for_visible_range(*args, **kwargs)
                
    def scale_visible_setup(self):
        self.optical_plotter.scale_visible_setup()
        
    def plot_optical_system_from_resonator(self, optical_system):
        self.optical_plotter.plot_optical_system_from_resonator(optical_system)
        
    def update_live_plot(self):
        """Update live plot with proper saving"""
        
        # Führe das Plot-Update durch
        self.optical_plotter.update_live_plot(self)
        # Verzögerte Speicherung um Race Conditions zu vermeiden
        QtCore.QTimer.singleShot(10, self.save_current_setup)
        if self.cursor_vline not in self.plotWidget.items():
            self.plotWidget.addItem(self.cursor_vline, ignoreBounds=True)
            self.cursor_vline.setZValue(100)

    def save_properties_to_component(self, component):
        """Debug-erweiterte Version"""
        if not component or not hasattr(self, '_property_fields'):
            return component
        
        self._saving_properties = True
        
        try:
            updated = copy.deepcopy(component)
            if "properties" not in updated:
                updated["properties"] = {}
            
            for key, field in self._property_fields.items():
                if isinstance(field, QtWidgets.QLineEdit):
                    old_value = updated["properties"].get(key, "N/A")
                    new_value = self.vc.convert_to_float(field.text())
                    updated["properties"][key] = new_value
                elif isinstance(field, QtWidgets.QCheckBox):
                    old_value = updated["properties"].get(key, "N/A")
                    new_value = field.isChecked()
                    updated["properties"][key] = new_value
                elif isinstance(field, QtWidgets.QComboBox):
                    old_value = updated["properties"].get(key, "N/A")
                    new_value = field.currentText()
                    updated["properties"][key] = new_value
                elif isinstance(field, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
                    old_value = updated["properties"].get(key, "N/A")
                    new_value = field.value()
                    updated["properties"][key] = new_value
            
            # Synchronisiere Beam-Properties in der gesamten setupList
            if updated.get("type", "").upper() == "BEAM" and hasattr(self, "setupList"):
                for i in range(self.setupList.count()):
                    item = self.setupList.item(i)
                    comp = item.data(QtCore.Qt.UserRole)
                    if isinstance(comp, dict) and comp.get("type", "").upper() == "BEAM":
                        comp["properties"] = copy.deepcopy(updated["properties"])
                        item.setData(QtCore.Qt.UserRole, comp)
        
        finally:
            self._saving_properties = False
        
        return updated
        
    def receive_setup(self, setup_components):
        """
        Empfängt ein Setup vom Resonator und fügt es zur Setup-Liste hinzu
        """
        if not setup_components:
            return
        
        try:
            # Speichere das aktuelle Setup bevor ein neues erstellt wird
            current_index = self.ui.comboBoxSetup.currentIndex()
            if 0 <= current_index < len(self.setups):
                current_setup = []
                for i in range(self.setupList.count()):
                    item = self.setupList.item(i)
                    comp = item.data(QtCore.Qt.UserRole)
                    if comp:
                        current_setup.append(copy.deepcopy(comp))
                self.setups[current_index]["components"] = current_setup
            
            # Finde die höchste Setup-Nummer
            existing_numbers = []
            for setup in self.setups:
                name = setup.get("name", "")
                if name.startswith("Setup "):
                    try:
                        num = int(name.split("Setup ")[1])
                        existing_numbers.append(num)
                    except (ValueError, IndexError):
                        pass
            
            # Bestimme die nächste verfügbare Nummer
            if existing_numbers:
                next_number = max(existing_numbers) + 1
            else:
                next_number = 1
            
            # Erstelle neues Setup mit Resonator-Komponenten
            new_setup_name = f"Setup {next_number}"
            
            # Füge das Resonator-Setup hinzu
            self.setups.append({"name": new_setup_name, "components": setup_components})
            
            # Aktualisiere ComboBox
            self.update_setup_names_and_combobox()
            
            # Wähle das neue Setup aus
            new_index = len(self.setups) - 1
            self.ui.comboBoxSetup.setCurrentIndex(new_index)
            
            # Lade das Setup in die setupList
            self.load_setup_into_list(setup_components)
            
            # Markiere als geändert
            self.mark_as_modified()
            
            # Aktualisiere den Plot
            self.update_live_plot()
            
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(
                self,
                "Error",
                f"Error adding resonator setup: {str(e)}"
            )

    def load_setup_into_list(self, components):
        """
        Lädt Komponenten in die setupList
        """
        
        # Liste leeren
        self.setupList.clear()
        
        # Komponenten hinzufügen
        for i, comp in enumerate(components):
            if comp:  # Prüfe auf None
                item_name = comp.get("name", f"Component {i}")
                item = QtWidgets.QListWidgetItem(item_name)
                item.setData(QtCore.Qt.UserRole, copy.deepcopy(comp))
                self.setupList.addItem(item)
        
        # Properties-Panel zurücksetzen
        self._last_component_item = None
        if hasattr(self, '_property_fields'):
            self._property_fields.clear()
    
    def receive_optimized_system(self, optimized_system):
        """Receive and process optimized lens system from modematcher"""
        try:
            # Leere die aktuelle Setup-Liste
            self.setupList.clear()
            
            # Füge alle Komponenten zur Setup-Liste hinzu
            for component in optimized_system:
                self.add_component_to_setup(component)
            
            if self.setupList.count() > 0:
                # Wähle das erste Item aus
                self.setupList.setCurrentRow(0)
                
                # Zeige Properties des ersten Items
                first_item = self.setupList.item(0)
                if first_item:
                    self.show_properties_for_selected_item()
                
                # Update Live Plot
                QtCore.QTimer.singleShot(100, self.update_live_plot)
            
            # Zeige Erfolgs-Nachricht
            QMessageBox.information(
                self,
                "Optimized System Loaded", 
                f"Loaded optimized lens system with {len(optimized_system)} components."
            )
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error receiving optimized system: {str(e)}")