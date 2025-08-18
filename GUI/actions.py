from PyQt5.QtWidgets import QFileDialog, QMessageBox
from PyQt5.QtCore import *
from PyQt5 import QtCore, QtWidgets
import copy
import json
import os
from datetime import datetime

class Action:
    def __init__(self):
        self.current_file_path = None
        # Definiere Projects-Ordner als Standard-Verzeichnis
        self.projects_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Projects")
        self._ensure_projects_dir()

    def _ensure_projects_dir(self):
        """Stelle sicher, dass der Projects-Ordner existiert."""
        if not os.path.exists(self.projects_dir):
            try:
                os.makedirs(self.projects_dir)
            except OSError as e:
                # Fallback auf aktuelles Verzeichnis
                self.projects_dir = os.getcwd()

    def _get_default_directory(self):
        """Gibt das Standard-Verzeichnis für Datei-Dialoge zurück."""
        return self.projects_dir

    def action_save(self, parent):
        """Speichert das aktuelle Setup. Verwendet Save As wenn noch kein Dateipfad vorhanden."""
        if self.current_file_path:
            return self._save_to_file(parent, self.current_file_path)
        else:
            return self.action_save_as(parent)

    def action_save_as(self, parent):
        """Öffnet Dialog zum Speichern des aktuellen Setups unter neuem Namen."""
        # Aktuellen Setup-Namen als Standardnamen verwenden
        current_setup_name = parent.ui.comboBoxSetup.currentText()
        default_name = current_setup_name.replace(" ", "_") + ".graycad"
        
        # Vollständiger Pfad mit Projects-Ordner
        default_path = os.path.join(self._get_default_directory(), default_name)
        
        file_name, _ = QFileDialog.getSaveFileName(
            parent, 
            "Save Setup As", 
            default_path,  # Verwende vollständigen Pfad
            "GRay-CAD Files (*.graycad);;JSON Files (*.json);;All Files (*)"
        )
        
        if file_name:
            success = self._save_to_file(parent, file_name)
            if success:
                self.current_file_path = file_name
                # Fenstertitel aktualisieren
                parent.setWindowTitle(f"GRay-CAD 2 - {os.path.basename(file_name)}")
            return success
        return False

    def action_open(self, parent):
        """Öffnet ein gespeichertes Setup."""
        file_name, _ = QFileDialog.getOpenFileName(
            parent, 
            "Open Setup", 
            self._get_default_directory(),  # Starte im Projects-Ordner
            "GRay-CAD Files (*.graycad);;JSON Files (*.json);;All Files (*)"
        )
        
        if file_name:
            return self._load_from_file(parent, file_name)
        return False

    def _save_to_file(self, parent, file_path):
        """Speichert das aktuelle Setup in die angegebene Datei. Rückgabe: bool."""
        try:
            # Sammle alle Komponenten aus der setupList
            components = []
            for i in range(parent.setupList.count()):
                item = parent.setupList.item(i)
                component = item.data(QtCore.Qt.UserRole)
                if isinstance(component, dict):
                    components.append(copy.deepcopy(component))

            setup_data = {
                "name": parent.ui.comboBoxSetup.currentText(),
                "created": datetime.now().isoformat(),
                "version": "0.1",
                "type": "GRAYCAD_SETUP",
                "components": components,
                "metadata": {
                    "component_count": len(components),
                    "has_beam": any(comp.get("name", "").strip().lower() == "beam" for comp in components),
                    "saved_from": "GRay-CAD 2"
                }
            }

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(setup_data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            QMessageBox.critical(parent, "Error", f"Failed to save setup:\n{str(e)}")
            return False

    def _load_from_file(self, parent, file_path):
        """Lädt ein Setup aus Datei und fügt es als neues Setup hinzu (löscht bestehende nicht). Rückgabe: bool."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                setup_data = json.load(f)
            if not isinstance(setup_data, dict) or "components" not in setup_data:
                raise ValueError("Invalid setup file format")
            components = setup_data.get("components", [])
            base_name = setup_data.get("name", os.path.basename(file_path))
            has_beam = any(comp.get("type", "").strip().lower() == "beam" for comp in components)
            if not has_beam:
                reply = QMessageBox.question(
                    parent, "No Beam Found",
                    "The loaded setup contains no beam component. Continue anyway?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return False
            if not hasattr(parent, 'setups'):
                parent.setups = []
            if hasattr(parent, 'ui') and hasattr(parent.ui, 'comboBoxSetup'):
                current_index = parent.ui.comboBoxSetup.currentIndex()
                if 0 <= current_index < len(getattr(parent, 'setups', [])):
                    current_components = []
                    for i in range(parent.setupList.count()):
                        item = parent.setupList.item(i)
                        comp = item.data(QtCore.Qt.UserRole)
                        if isinstance(comp, dict):
                            current_components.append(copy.deepcopy(comp))
                    try:
                        parent.setups[current_index]['components'] = current_components
                    except Exception:
                        pass
            existing_names = {s.get("name", "") for s in parent.setups}
            name = base_name
            if name in existing_names:
                k = 2
                while f"{base_name} ({k})" in existing_names:
                    k += 1
                name = f"{base_name} ({k})"
            new_setup = {"name": name, "components": copy.deepcopy(components)}
            parent.setups.append(new_setup)
            if hasattr(parent.ui, 'comboBoxSetup'):
                parent.ui.comboBoxSetup.addItem(name)
                parent.ui.comboBoxSetup.setCurrentIndex(parent.ui.comboBoxSetup.count() - 1)
            parent.setupList.clear()
            parent._last_component_item = None
            if hasattr(parent, '_property_fields'):
                parent._property_fields.clear()
            for comp in components:
                item = QtWidgets.QListWidgetItem(comp.get("name", "Unnamed"))
                item.setData(QtCore.Qt.UserRole, copy.deepcopy(comp))
                parent.setupList.addItem(item)
            parent.update_live_plot()
            if hasattr(parent, 'scale_visible_setup'):
                parent.scale_visible_setup()
            self.current_file_path = file_path
            parent.setWindowTitle(f"GRay-CAD 2 - {os.path.basename(file_path)}")
            return True
        except Exception as e:
            QMessageBox.critical(parent, "Error", f"Failed to load setup:\n{str(e)}")
            return False

    def action_new(self, parent):
        """Erstellt ein neues Setup."""
        if parent.setupList.count() > 0:
            reply = QMessageBox.question(
                parent,
                "New Setup",
                "Create new setup? Unsaved changes will be lost.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return False

        # Lade Standard-Komponenten
        parent.setupList.clear()
        parent.create_new_setup()
        self.current_file_path = None
        parent.setWindowTitle("GRay-CAD 2 - New Setup")
        return True

    def action_about(self, parent):
        QMessageBox.information(
            parent, 
            "About", 
            "GRay-CAD 2\nVersion 0.1 the forever development release\nDeveloped by Jens Gumm, TU Darmstadt, LQO-Group"
        )

    def action_tips_and_tricks(self, parent):
        """
        Handles the 'Tips and Tricks' menu action.
        Displays helpful tips for using the application.
        """
        msg = QMessageBox(parent)
        msg.setWindowTitle("Tips and Tricks")
        msg.setTextFormat(Qt.RichText)
        msg.setTextInteractionFlags(Qt.TextBrowserInteraction)
        msg.setIcon(QMessageBox.Information)
        msg.setText(
            "1. Use the Edit/Library to manage your components.<br>"
            "2. You can drag and drop components into the setup list.<br>"
            "3. If you dont type a unit, it will be interpreted as meters.<br>"
            "4. Take advantage of the simulation features like the Modematcher and the Cavity Designer.<br>"
            "5. Don't forget to save your work!<br>"
            '6. Report bugs on GitHub: <a href="https://github.com/NiceLaserGuy/GRay-CAD-2">https://github.com/NiceLaserGuy/GRay-CAD-2</a>'
        )
        msg.exec()

    def action_exit(self, parent):
        reply = QMessageBox.question(
            parent, 
            "Exit", 
            "Do you really want to close the program? All unsaved data will be lost!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            parent.close()

    def handle_build_resonator(self, parent):
        """
        Handles the 'Build Resonator' button action.
        Sets the current context to 'resonator' and opens the library window.
        """
        parent.current_context = "resonator"
        parent.item_selector_res.open_library_window(parent)

    def handle_modematcher(self, parent):
        """
        Handles the 'Modematcher' button action.
        Sets the current context to 'modematcher' and opens the library window.
        """
        parent.current_context = "modematcher"
        parent.item_selector_modematcher.open_library_window()

    def delete_selected_setup_item(self, parent):
        for item in parent.setupList.selectedItems():
            row = parent.setupList.row(item)
            # Beam (immer an Position 0) darf nicht gelöscht werden
            if row == 0:
                continue
            parent.setupList.takeItem(row)

    def move_selected_setup_item_up(self, parent):
        listw = parent.setupList
        items = listw.selectedItems()
        if not items:
            return
        item = items[0]
        row = listw.row(item)
        # Beam (immer an Position 0) darf nicht verschoben werden
        if row <= 1:
            return
        listw.takeItem(row)
        listw.insertItem(row - 1, item)
        listw.setCurrentItem(item)

    def move_selected_setup_item_down(self, parent):
        listw = parent.setupList
        items = listw.selectedItems()
        if not items:
            return
        item = items[0]
        row = listw.row(item)
        # Beam (immer an Position 0) darf nicht verschoben werden
        if row == 0 or row >= listw.count() - 1:
            return
        listw.takeItem(row)
        listw.insertItem(row + 1, item)
        listw.setCurrentItem(item)
    
    def is_beam_item(self, item):
        component = item.data(0, QtCore.Qt.UserRole)
        if not isinstance(component, dict):
            return False
        return component.get("type", "").lower() == "beam"
    
    def move_selected_component_to_setupList(self, parent):
        # Hole das aktuell ausgewählte Item aus der componentList
        items = parent.componentList.selectedItems()
        if not items:
            return
        item = items[0]
        component = item.data(QtCore.Qt.UserRole)
        if not isinstance(component, dict):
            return

        is_beam = (
            component.get("name", "").strip().lower() == "beam"
            or component.get("type", "").strip().lower() == "beam"
        )
        # Prüfe, ob schon ein Beam in setupList existiert
        if is_beam:
            for i in range(parent.setupList.count()):
                c = parent.setupList.item(i).data(QtCore.Qt.UserRole)
                if isinstance(c, dict) and (
                    c.get("name", "").strip().lower() == "beam"
                    or c.get("type", "").strip().lower() == "beam"
                ):
                    return  # Kein zweiter Beam erlaubt

        # Füge das Item nur EINMAL in setupList ein (mit deepcopy!)
        new_item = QtWidgets.QListWidgetItem(component.get("name", "Unnamed"))
        new_item.setData(QtCore.Qt.UserRole, copy.deepcopy(component))
        if is_beam:
            parent.setupList.insertItem(0, new_item)
        else:
            parent.setupList.addItem(new_item)
        parent.setupList.setCurrentItem(new_item)

    def get_recent_files(self, max_files=5):
        """Hole die letzten verwendeten Dateien aus dem Projects-Ordner."""
        try:
            files = []
            for file in os.listdir(self.projects_dir):
                if file.endswith('.graycad'):
                    full_path = os.path.join(self.projects_dir, file)
                    files.append((full_path, os.path.getmtime(full_path)))
            
            # Sortiere nach Änderungsdatum (neueste zuerst)
            files.sort(key=lambda x: x[1], reverse=True)
            return [f[0] for f in files[:max_files]]
        except:
            return []
        
    def create_auto_backup(self, parent):
        """Erstelle automatisches Backup im Projects-Ordner."""
        backup_dir = os.path.join(self.projects_dir, "backups")
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"auto_backup_{timestamp}.graycad"
        backup_path = os.path.join(backup_dir, backup_name)
        
        return self._save_to_file(parent, backup_path)
    
    def create_project_templates(self):
        """Erstelle Standard-Projekt-Vorlagen im Projects-Ordner."""
        templates_dir = os.path.join(self.projects_dir, "templates")
        if not os.path.exists(templates_dir):
            os.makedirs(templates_dir)
        
        # Standard-Vorlagen definieren
        templates = {
            "Basic_Beam.graycad": {
                "name": "Basic Beam Setup",
                "components": [
                    {
                        "type": "BEAM",
                        "name": "Beam",
                        "properties": {
                            "Wavelength": 632.8e-9,
                            "Waist radius sagittal": 1e-3,
                            "Waist radius tangential": 1e-3
                        }
                    }
                ]
            },
            "Simple_Lens_System.graycad": {
                "name": "Simple Lens System",
                "components": [
                    # Beam + Propagation + Lens + Propagation
                ]
            }
        }
        
        for filename, template in templates.items():
            template_path = os.path.join(templates_dir, filename)
            if not os.path.exists(template_path):
                with open(template_path, 'w') as f:
                    json.dump(template, f, indent=2)

    def get_projects_info(self):
        """Hole Informationen über alle Projekte im Projects-Ordner."""
        projects = []
        try:
            for file in os.listdir(self.projects_dir):
                if file.endswith('.graycad'):
                    full_path = os.path.join(self.projects_dir, file)
                    try:
                        with open(full_path, 'r') as f:
                            data = json.load(f)
                        projects.append({
                            "filename": file,
                            "name": data.get("name", file),
                            "created": data.get("created", "Unknown"),
                            "component_count": data.get("metadata", {}).get("component_count", 0),
                            "has_beam": data.get("metadata", {}).get("has_beam", False)
                        })
                    except:
                        # Fehlerhaft Datei überspringen
                        continue
        except:
            pass
        return projects

    def create_default_setup_file(self):
        """Erstelle Default-Setup-Datei falls sie nicht existiert."""
        default_setup_path = os.path.join(self.projects_dir, "templates", "default_setup.graycad")
        
        if not os.path.exists(default_setup_path):
            # Erstelle Templates-Verzeichnis
            os.makedirs(os.path.dirname(default_setup_path), exist_ok=True)
            
            # VERWENDE die statische Methode
            from GUI.setupList import SetupList
            components = SetupList.get_default_components()
            
            # Standard-Setup definieren
            default_setup = {
                "name": "Default Setup",
                "created": datetime.now().isoformat(),
                "version": "2.0",
                "type": "GRAYCAD_SETUP",
                "components": components
            }
            
            try:
                with open(default_setup_path, 'w', encoding='utf-8') as f:
                    json.dump(default_setup, f, indent=2, ensure_ascii=False)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not create default setup file: {e}")