import json, tempfile
from os import path, listdir
from PyQt5 import uic, QtWidgets
from PyQt5.QtWidgets import QMainWindow, QMessageBox
from PyQt5.QtCore import QModelIndex, QObject
from PyQt5.QtGui import QStandardItemModel, QStandardItem

from src_resonator.resonators import Resonator
from src_physics.value_converter import ValueConverter
from GUI.properties_handler import PropertiesHandler
import config

class LibraryWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.item_selector = None  # Reference to ItemSelector
        

    def closeEvent(self, event):
        """
        Called when the window is about to be closed (X button).
        """
        event.ignore()  # Prevent default closing
        if self.item_selector:
            self.item_selector.handle_back_button()

class ItemSelector(QObject, PropertiesHandler):
    def __init__(self, parent=None):
        QObject.__init__(self, parent)
        PropertiesHandler.__init__(self, live_plot_callback=None)
        
        self.library_window = None
        self.ui_select_component_window = None
        self.components_data = []  # Store components data
        
        self.res = Resonator()

        self._last_component_item = None

    def open_library_window(self, parent=None):
        """
        Creates and shows the library window.
        """
        self.library_window = parent  # Store main window reference
        self.lib_resonator_window = LibraryWindow(parent)  # Create new window with main window as parent
        self.lib_resonator_window.item_selector = self
    
        # Load the library UI
        ui_path = path.abspath(path.join(path.dirname(path.dirname(__file__)), "assets/select_component_window.ui"))
        self.ui_select_component_window = uic.loadUi(ui_path, 
            self.lib_resonator_window
        )
        if hasattr(self.ui_select_component_window, 'propertyLayout'):
            self.propertyLayout = self.ui_select_component_window.propertyLayout
        else:
            # Optional: Erstelle ein GridLayout
            self.propertyLayout = QtWidgets.QGridLayout()
        
        # Configure and show the window
        self.lib_resonator_window.setWindowTitle("Select Components")
        self.lib_resonator_window.show()
        
        # Connect the next button to the method
        self.ui_select_component_window.button_next.clicked.connect(self.handle_next_button)

        # Load files from the Library folder and display them
        self.load_library_files()

        # Connect the listView_libraries to a click event
        self.ui_select_component_window.listView_libraries.clicked.connect(self.display_file_contents)
        
        # Connect the listView_lib_components to a click event
        self.ui_select_component_window.listView_lib_components.clicked.connect(self.display_component_details)
        
        # NEU: Connect the listView_temporary_component to a click event
        self.ui_select_component_window.listView_temporary_component.clicked.connect(self.display_temporary_component_details)
        
        # Connect the pushButton_add_all to the method
        self.ui_select_component_window.pushButton_add_all.clicked.connect(self.add_all_components_to_temporary_list)
        
        # Connect the pushButton_add to the method
        self.ui_select_component_window.toolButton_add_component.clicked.connect(self.add_component_to_temporary_list)
        
        self.ui_select_component_window.pushButton_remove_component.clicked.connect(self.remove_component_from_temporary_list)
    
        self.ui_select_component_window.pushButton_remove_all.clicked.connect(self.remove_all_components_from_temporary_list)

        self.ui_select_component_window.button_back.clicked.connect(self.close_library_window)
    
    def handle_next_button(self):
        """
        Saves the temporary file and performs actions based on context.
        Creates a new window on first call, shows hidden window on subsequent calls.
        """
        self._save_current_component_properties()
        # Save temporary file und prüfe Rückgabewert
        if not self.save_temporary_file():
            return  # Abbrechen, wenn nichts gespeichert wurde

        # Hide current window
        if self.lib_resonator_window:
            self.lib_resonator_window.hide()

        # Execute action based on context
        if self.parent().current_context == "resonator":
            if not hasattr(self.res, 'resonator_window') or self.res.resonator_window is None:
                # First time - create new window
                self.res.open_resonator_window()
            else:
                # Window exists - show again
                self.res.resonator_window.show()
                self.res.resonator_window.raise_()  # Bring window to front
            # Pass reference to current window
            self.res.previous_window = self.lib_resonator_window
        elif self.parent().current_context == "modematcher":
            if not hasattr(self.parent().modematcher, 'modematcher_window') or self.parent().modematcher.modematcher_window is None:
                self.parent().modematcher.open_modematcher_parameter_window()
                self.parent().modematcher.previous_window = self.lib_resonator_window  # Add this line
            else:
                self.parent().modematcher.modematcher_window.show()
                self.parent().modematcher.modematcher_window.raise_()
        else:
            QMessageBox.warning(
                self.library_window,
                "Unknown Context",
                "No valid context recognized."
            )
            
    def _save_current_component_properties(self):
        """
        Speichert die aktuell bearbeiteten Properties in die temporäre Liste
        """
        if (hasattr(self, '_current_temp_component_index') and 
            hasattr(self, '_current_temp_component') and
            hasattr(self, '_property_fields') and
            self._property_fields):
            
            # Aktualisiere die Komponente mit den aktuellen Property-Werten
            updated_component = self.save_properties_to_component(self._current_temp_component)
            if updated_component and hasattr(self, 'temporary_components'):
                # Ersetze die Komponente in der temporären Liste
                self.temporary_components[self._current_temp_component_index] = updated_component
                
                # Aktualisiere die temporäre Datei
                self.update_temporary_file()

    def close_library_window(self):
        """
        Closes the library window.
        """
        if self.lib_resonator_window:
            self.ui_select_component_window.close()
        if self.parent():
            self.parent().show()
     
    def load_library_files(self):
        """
        Loads files from the 'Library' folder and displays them in the listView_libraries.
        """
        # Path to the Library folder
        library_path = path.abspath(path.join(path.dirname(path.dirname(__file__)), "Library"))

        # Check if the folder exists
        if not path.exists(library_path):
            QMessageBox.warning(
                self.library_window,
                "Library Folder Not Found",
                f"Library folder not found: {library_path}"
            )
            return

        # Get a list of files in the Library folder
        files = [f for f in listdir(library_path) if path.isfile(path.join(library_path, f))]

        # Create a model for the listView
        model = QStandardItemModel()

        # Add files to the model
        for file_name in files:
            item = QStandardItem(file_name)
            model.appendRow(item)

        # Set the model to the listView
        self.ui_select_component_window.listView_libraries.setModel(model)
               
    def display_file_contents(self, index: QModelIndex):
        """
        Displays the 'components' entries of the selected file in the listView_lib_components.
        Sets up the data for further interaction.
        """
        # Get the selected file name
        selected_file = index.data()

        # Path to the Library folder
        library_path = path.abspath(path.join(path.dirname(path.dirname(__file__)), "Library"))
        file_path = path.join(library_path, selected_file)

        # Check if the file exists
        if not path.exists(file_path):
            QMessageBox.warning(
                self.library_window,
                "File Not Found",
                f"File not found: {file_path}"
            )
            return

        # Read the contents of the file
        try:
            with open(file_path, 'r') as file:
                data = json.load(file)  # Parse the JSON file
        except Exception as e:
            QMessageBox.critical(
                self.library_window,
                "Error Reading File",
                f"An error occurred while reading the file: {e}"
            )
            return

        # Create a model for the listView_lib_components
        model = QStandardItemModel()

        # Extract and display the 'components' entries
        self.components_data = []  # Clear previous data
        if "components" in data and isinstance(data["components"], list):
            for component in data["components"]:
                # Check if the component has a 'name' attribute
                if "name" in component:
                    item = QStandardItem(component["name"])  # Add the 'name' of the component to the list
                    model.appendRow(item)
                    self.components_data.append(component)  # Store the full component data
                else:
                    QMessageBox.warning(
                        self.library_window,
                        "Component Missing Name",
                        f"Component without 'name' attribute found: {component}"
                    )
        else:
            QMessageBox.warning(
                self.library_window,
                "No Components Found",
                f"No 'components' list found in {selected_file}"
            )

        # Set the model to the listView_lib_components
        self.ui_select_component_window.listView_lib_components.setModel(model)

        # Connect the listView_lib_components to a click event
        self.ui_select_component_window.listView_lib_components.clicked.connect(self.display_component_details)
        
    def display_component_details(self, index: QModelIndex):
        """
        Displays the details of the selected component using the modern properties system.
        """
        selected_index = index.row()

        if 0 <= selected_index < len(self.components_data):
            component = self.components_data[selected_index]
            
            # NEU: Verwende das moderne Properties-System
            self._last_component_item = None  # Reset für ItemSelector
            
            # Dynamisch Properties hinzufügen für Linsen (wie in graycad_mainwindow)
            ctype = component.get("type", "").strip().upper()
            props = component.get("properties", {})
            
            if ctype == "LENS":
                if "Variable parameter" not in props:
                    props["Variable parameter"] = "Edit focal length"
                if "Plan lens" not in props:
                    props["Plan lens"] = False
                if "Lens material" not in props:
                    props["Lens material"] = "NBK7"
                component["properties"] = props

            # Zeige Properties mit dem modernen System
            if hasattr(self, 'propertyLayout'):
                self.show_properties(props, component)
          
            # Behalte nur diese für Rückwärtskompatibilität:
            if hasattr(self.ui_select_component_window, 'labelName'):
                self.ui_select_component_window.labelName.setText(component.get("name", ""))
            if hasattr(self.ui_select_component_window, 'labelManufacturer'):
                self.ui_select_component_window.labelManufacturer.setText(component.get("manufacturer", ""))
            if hasattr(self.ui_select_component_window, 'labelType'):
                self.ui_select_component_window.labelType.setText(component.get("type", ""))
            
            
        else:
            QMessageBox.warning(
                self.library_window,
                "Invalid Component Index",
                f"Invalid component index: {selected_index}"
            )
            
    def toggle_curvature_tangential(self, checked):
        """
        Toggles the enabled state of the edit_curvature_tangential field
        based on the state of the checkBox_is_spherical.
        
        Args:
            checked (bool): True if the radio button is checked, False otherwise.
        """
        self.ui_select_component_window.edit_curvature_tangential.setEnabled(not checked)
        self.ui_select_component_window.label_6.setEnabled(not checked)
        if checked:
            # Set the value of edit_curvature_tangential to match edit_curvature_sagittal
            curvature_sagittal = self.ui_select_component_window.edit_curvature_sagittal.text().strip()
            self.ui_select_component_window.edit_curvature_tangential.setText(curvature_sagittal)
            self.ui_select_component_window.edit_curvature_tangential.setEnabled(False)  # Disable the field
        else:
            self.ui_select_component_window.edit_curvature_tangential.setEnabled(True)  # Enable the field

    def save_temporary_file(self):
        """
        Saves the temporary list to a temporary file.
        This method is called when clicking the next button.
        """
        if not hasattr(self, "temporary_components") or not self.temporary_components:
            QMessageBox.warning(
                self.library_window,
                "No Components to Save",
                "There are no components to save."
            )
            return False  # <--- Änderung: False zurückgeben

        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8")
        self.temp_file_path = temp_file.name

        try:
            # Save as dictionary with key "components"
            json.dump({"components": self.temporary_components}, temp_file, indent=4)
            temp_file.close()
        except Exception as e:
            QMessageBox.critical(
                self.library_window,
                "Error Saving File",
                f"Error while saving temporary file: {e}"
            )
            return

        # Set global variable
        config.set_temp_file_path(self.temp_file_path)
        
        return True  # <--- Erfolg

    def display_temporary_file(self, temp_file_path):
        """
        Zeigt die temporäre Datei in der listView_temporary_component an.
        """
        # Erstellen eines Modells für die listView
        model = QStandardItemModel()

        # Temporäre Datei zur Liste hinzufügen
        item = QStandardItem(temp_file_path)
        model.appendRow(item)

        # Modell in der listView setzen (Widget-Name anpassen, falls erforderlich)
        self.ui_select_component_window.listView_temporary_component.setModel(model)
        
    def add_component_to_temporary_list(self):
        """
        Fügt die ausgewählte Komponente zur temporären Liste hinzu.
        """
        selected_indexes = self.ui_select_component_window.listView_lib_components.selectedIndexes()
        if not selected_indexes:
            QMessageBox.warning(
                self.library_window,
                "No Component Selected",
                "Bitte wählen Sie eine Komponente aus der Liste aus."
            )
            return

        selected_index = selected_indexes[0].row()
        if 0 <= selected_index < len(self.components_data):
            selected_component = self.components_data[selected_index].copy()
            
            # NEU: Verwende save_properties_to_component für aktuelle Werte
            if hasattr(self, '_property_fields') and self._property_fields:
                updated_component = self.save_properties_to_component(selected_component)
                if updated_component:
                    selected_component = updated_component
        
        else:
            QMessageBox.warning(
                self.library_window,
                "Invalid Selection",
                "Die ausgewählte Komponente ist ungültig."
            )
            return

        # Füge die Komponente zur temporären Liste hinzu
        if not hasattr(self, "temporary_components"):
            self.temporary_components = []
        self.temporary_components.append(selected_component)

        # Aktualisiere die temporäre Datei und Liste
        self.update_temporary_file()
        self.update_temporary_list_view()

    def update_temporary_file(self):
        """
        Speichert die temporäre Liste in einer temporären Datei.
        """
        # Temporäre Datei erstellen
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8")
        self.temp_file_path = temp_file.name

        # Daten in die temporäre Datei schreiben
        try:
            json.dump({"components": self.temporary_components}, temp_file, indent=4)
            temp_file.close()
        except Exception as e:
            QMessageBox.critical(
                self.library_window,
                "Error Saving File",
                f"Fehler beim Speichern der temporären Datei: {e}"
            )
            return

        # Setzen der globalen Variable
        config.TEMP_FILE_PATH = self.temp_file_path

    def update_temporary_list_view(self):
        """
        Zeigt die temporäre Liste in listView_temporary_component an.
        """
        model = QStandardItemModel()
        if hasattr(self, "temporary_components") and self.temporary_components:
            # Füge die Namen der Komponenten zur Liste hinzu
            for component in self.temporary_components:
                item_name = component.get("name", "Unbenannte Komponente")
                item = QStandardItem(item_name)
                model.appendRow(item)
        # Setze das Modell in listView_temporary_component (immer!)
        self.ui_select_component_window.listView_temporary_component.setModel(model)

    def add_all_components_to_temporary_list(self):
        """
        Fügt alle Komponenten aus listView_lib_components zur temporären Liste hinzu
        und speichert sie in der temporären Datei.
        """
        if not self.components_data:
            QMessageBox.warning(
                self.library_window,
                "No Components Available",
                "Es gibt keine Komponenten, die hinzugefügt werden können."
            )
            return

        # Initialisiere die temporäre Liste, falls sie nicht existiert
        if not hasattr(self, "temporary_components"):
            self.temporary_components = []

        # Füge alle Komponenten aus components_data zur temporären Liste hinzu
        self.temporary_components.extend(self.components_data)

        # Entferne Duplikate (optional, falls erforderlich)
        self.temporary_components = list({comp["name"]: comp for comp in self.temporary_components}.values())

        # Aktualisiere die temporäre Datei
        self.update_temporary_file()

        # Zeige die temporäre Liste in listView_temporary_component an
        self.update_temporary_list_view()

    def remove_component_from_temporary_list(self):
        """
        Entfernt die ausgewählte Komponente aus der temporären Liste.
        """
        # Überprüfen, ob eine Komponente ausgewählt ist
        selected_indexes = self.ui_select_component_window.listView_temporary_component.selectedIndexes()
        if not selected_indexes:
            QMessageBox.warning(
                self.library_window,
                "No Component Selected",
                "Bitte wählen Sie eine Komponente aus der temporären Liste aus."
            )
            return

        # Hole den Index der ausgewählten Komponente
        selected_index = selected_indexes[0].row()

        # Überprüfen, ob der Index gültig ist
        if 0 <= selected_index < len(self.temporary_components):
            # Entferne die Komponente aus der temporären Liste
            self.temporary_components.pop(selected_index)

        else:
            QMessageBox.warning(
                self.library_window,
                "Invalid Selection",
                "Die ausgewählte Komponente ist ungültig."
            )
            return

        # Aktualisiere die Anzeige der temporären Liste
        if not self.temporary_components:
            # Wenn die Liste leer ist, setze ein leeres Modell
            self.ui_select_component_window.listView_temporary_component.setModel(QStandardItemModel())
        else:
            # Aktualisiere die temporäre Datei und Liste
            self.update_temporary_file()
            self.update_temporary_list_view()

    def remove_all_components_from_temporary_list(self):
        """
        Entfernt alle Komponenten aus der temporären Liste.
        """
        # Überprüfen, ob die temporäre Liste leer ist
        if not hasattr(self, "temporary_components") or not self.temporary_components:
            QMessageBox.warning(
                self.library_window,
                "No Components to Remove",
                "Es gibt keine Komponenten, die entfernt werden können."
            )
            return

        # Leere die temporäre Liste
        self.temporary_components.clear()

        # Aktualisiere die temporäre Datei
        self.update_temporary_file()

        # Aktualisiere die Anzeige der temporären Liste
        self.update_temporary_list_view()
        
        # Setze ein leeres Modell für die listView_temporary_component
        self.ui_select_component_window.listView_temporary_component.setModel(QStandardItemModel())

    def handle_back_button(self):
        """
        Verbirgt das aktuelle Fenster und zeigt das vorherige Fenster wieder an.
        """
        # Hole das Hauptfenster über parent()
        main_window = self.parent()
        
        if self.lib_resonator_window:
            self.lib_resonator_window.hide()  # Verbirgt das aktuelles Fenster
            
        if main_window:
            main_window.show()  # Zeigt das Hauptfenster
            main_window.raise_()  # Bringt das Hauptfenster in den Vordergrund

    def display_temporary_component_details(self, index: QModelIndex):
        """
        Displays the details of the selected component from the temporary list.
        """
        selected_index = index.row()

        if not hasattr(self, "temporary_components") or not self.temporary_components:
            QMessageBox.warning(
                self.library_window,
                "No Temporary Components",
                "Es gibt keine temporären Komponenten."
            )
            return

        if 0 <= selected_index < len(self.temporary_components):
            component = self.temporary_components[selected_index]
            
            # NEU: Verwende das moderne Properties-System
            self._last_component_item = None  # Reset für ItemSelector
            
            # Dynamisch Properties hinzufügen für Linsen (wie in graycad_mainwindow)
            ctype = component.get("type", "").strip().upper()
            props = component.get("properties", {})
            
            if ctype == "LENS":
                if "Variable parameter" not in props:
                    props["Variable parameter"] = "Edit focal length"
                if "Plan lens" not in props:
                    props["Plan lens"] = False
                if "Lens material" not in props:
                    props["Lens material"] = "NBK7"
                component["properties"] = props

            # Zeige Properties mit dem modernen System
            if hasattr(self, 'propertyLayout'):
                self.show_properties(props, component)
                
            # NEU: Speichere Referenz zur aktuellen temporären Komponente
            self._current_temp_component_index = selected_index
            self._current_temp_component = component
          
            # Behalte nur diese für Rückwärtskompatibilität:
            if hasattr(self.ui_select_component_window, 'labelName'):
                self.ui_select_component_window.labelName.setText(component.get("name", ""))
            if hasattr(self.ui_select_component_window, 'labelManufacturer'):
                self.ui_select_component_window.labelManufacturer.setText(component.get("manufacturer", ""))
            if hasattr(self.ui_select_component_window, 'labelType'):
                self.ui_select_component_window.labelType.setText(component.get("type", ""))
            
        else:
            QMessageBox.warning(
                self.library_window,
                "Invalid Component Index",
                f"Invalid temporary component index: {selected_index}"
            )
