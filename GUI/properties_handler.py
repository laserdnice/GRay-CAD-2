from PyQt5 import QtWidgets, QtCore
import numpy as np
from src_physics.value_converter import ValueConverter
from src_physics.material import Material
import copy

class PropertiesHandler:
    """
    Gemeinsame Klasse für Properties-Management.
    Kann von MainWindow und ItemSelector verwendet werden.
    """
    
    def __init__(self, live_plot_callback=None):
        self.vc = ValueConverter()
        self.material = Material
        self._property_fields = {}
        self._saving_properties = False
        self.live_plot_callback = live_plot_callback
        
        # Timer für Properties-Updates erstellen, aber NICHT verbinden
        self._property_update_timer = QtCore.QTimer()
        self._property_update_timer.setSingleShot(True)
        self._property_update_timer.setInterval(100)
        
    def _connect_timer(self):
        """Verbinde den Timer nach der vollständigen Initialisierung"""
        if hasattr(self, 'update_rayleigh'):
            self._property_update_timer.timeout.connect(self.update_rayleigh)
            
    def show_properties(self, properties: dict, component=None):
        layout: QtWidgets.QGridLayout = self.propertyLayout
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self._property_fields = {}
        row = 0

        # Definiere Paare (nur einmal zentral)
        paired_props = [
        ("Waist radius sagittal", "Waist radius tangential", "Waist radius"),
        ("Waist position sagittal", "Waist position tangential", "Waist position"),
        ("Rayleigh range sagittal", "Rayleigh range tangential", "Rayleigh range"),
        ("Focal length sagittal", "Focal length tangential", "Design focal length"),
        ("Radius of curvature sagittal", "Radius of curvature tangential", "Radius of curvature"),
        ("Input radius of curvature sagittal", "Input radius of curvature tangential", "Input radius of curvature"),  # Für THICK LENS
        ("Output radius of curvature sagittal", "Output radius of curvature tangential", "Output radius of curvature"),  # Für THICK LENS
        ("A sagittal", "A tangential", "A"),
        ("B sagittal", "B tangential", "B"),
        ("C sagittal", "C tangential", "C"),
        ("D sagittal", "D tangential", "D")
    ]

        # Set zum schnellen Nachschlagen
        paired_keys = set()
        for sag, tan, _ in paired_props:
            paired_keys.add(sag)
            paired_keys.add(tan)

        # Zeige Paare in einer Zeile
        for sag_key, tan_key, display_name in paired_props:
            if sag_key in properties or tan_key in properties:
                label = QtWidgets.QLabel(display_name + ":")
                layout.addWidget(label, row, 0)
                # Sagittal
                if sag_key in properties:
                    value = properties.get(sag_key, "")
                    field_sag = QtWidgets.QLineEdit(self.vc.convert_to_nearest_string(value))
                    layout.addWidget(field_sag, row, 1)
                    self._property_fields[sag_key] = field_sag
                    field_sag.textChanged.connect(self.make_field_slot(sag_key, component))
                    field_sag.returnPressed.connect(self.make_enter_slot(sag_key, component))
                    field_sag.editingFinished.connect(lambda: self.on_property_field_changed(component))
                else:
                    layout.addWidget(QtWidgets.QLabel(""), row, 1)
                # Tangential
                if tan_key in properties:
                    value = properties.get(tan_key, "")
                    field_tan = QtWidgets.QLineEdit(self.vc.convert_to_nearest_string(value))
                    layout.addWidget(field_tan, row, 2)
                    self._property_fields[tan_key] = field_tan
                    field_tan.textChanged.connect(self.make_field_slot(tan_key, component))
                    field_tan.returnPressed.connect(self.make_enter_slot(tan_key, component))
                    field_tan.editingFinished.connect(lambda: self.on_property_field_changed(component))
                else:
                    layout.addWidget(QtWidgets.QLabel(""), row, 2)
                row += 1

        # Zeige alle anderen Properties einzeln
        for key, value in properties.items():
            if key in paired_keys:
                continue  # Schon als Paar behandelt
            if key == "Refractive index" and "Lens material" in properties:
                continue
            if key == "IS_ROUND":
                label = QtWidgets.QLabel("Spherical:")
            elif key == "Plan lens":
                label = QtWidgets.QLabel("Plan lens:")
            else:
                # NEU: Spezielle Beschriftung für den Einfallswinkel
                if key == "Angle of incidence":
                    label = QtWidgets.QLabel("Angle of incidence (°):")  # Zeigt Grad-Symbol
                else:
                    label = QtWidgets.QLabel(key + ":")
            layout.addWidget(label, row, 0)
            # Checkbox für boolsche Werte
            if isinstance(value, (int, float)) and (key.startswith("IS_") or key.lower() == "is_round" or key == "Plan lens"):
                field = QtWidgets.QCheckBox()
                field.setChecked(bool(value))
                layout.addWidget(field, row, 1)
                self._property_fields[key] = field
                field.stateChanged.connect(self.make_checkbox_slot(key, component))
                # Beispiel für QCheckBox
                field.stateChanged.connect(lambda: self.on_property_field_changed(component))
                row += 1  # Zeile erhöhen nach Erstellen des Felds
                continue
                
            # Rayleigh range Felder immer readonly und grau
            elif "Rayleigh range" in key:
                field = QtWidgets.QLineEdit(self.vc.convert_to_nearest_string(value))
                field.setReadOnly(True)
                field.setStyleSheet("background-color: #eee; color: #888;")
                layout.addWidget(field, row, 1)
                self._property_fields[key] = field
                
            # Refractive index: Zahl oder Dropdown
            elif key == "Refractive index":
                field = QtWidgets.QLineEdit(str(value))
                layout.addWidget(field, row, 1)
                self._property_fields[key] = field
                field.textChanged.connect(self.make_field_slot(key, component))

            elif key == "Lens material":
                field = QtWidgets.QComboBox()
                field.addItems(["NBK7", "Fused Silica"])
                if value in ["NBK7", "Fused Silica"]:
                    field.setCurrentText(value)
                layout.addWidget(field, row, 1)
                self._property_fields[key] = field

                def on_lens_material_changed():
                    # Properties speichern
                    self.save_properties_to_component(component)
                    # System/Cache invalidieren falls Plotter vorhanden
                    if hasattr(self, 'optical_plotter') and hasattr(self.optical_plotter, 'mark_system_dirty'):
                        self.optical_plotter.mark_system_dirty()
                    # Live-Plot neu aufbauen
                    self.update_live_plot_delayed()
                field.currentIndexChanged.connect(on_lens_material_changed)
                # Weiterhin generische Behandlung (falls zusätzliche Logik greift)
                field.currentIndexChanged.connect(lambda: self.on_property_field_changed(component))
             
            # Ausgrauen der nicht benötigten Felder       
            elif key == "Variable parameter":
                field = QtWidgets.QComboBox()
                field.addItems(["Edit both curvatures", "Edit focal length"])
                if value in ["Edit both curvatures", "Edit focal length"]:
                    field.setCurrentText(value)
                layout.addWidget(field, row, 1)
                self._property_fields[key] = field
                def on_index_changed():
                    self.save_properties_to_component(component)
                    self.update_field_states()
                    self.update_live_plot_delayed()
                field.currentIndexChanged.connect(on_index_changed)
                # Beispiel für QComboBox
                field.currentIndexChanged.connect(lambda: self.on_property_field_changed(component))
                
            # Standard: QLineEdit
            else:
                try:
                    # SPEZIELLE BEHANDLUNG FÜR WINKEL
                    if key == "Angle of incidence":
                        # Konvertiere von Radiant zu Grad für die Anzeige
                        if isinstance(value, (int, float)):
                            display_value = np.rad2deg(value)
                            field = QtWidgets.QLineEdit(f"{display_value:.3f}")  # Ohne Einheit, nur Zahl
                        else:
                            field = QtWidgets.QLineEdit(str(value))
                    else:
                        # Normale Behandlung für andere Felder
                        field = QtWidgets.QLineEdit(self.vc.convert_to_nearest_string(value))
                except ValueError:
                    field = QtWidgets.QLineEdit(str(value))  # Fallback für nicht konvertierbare Werte
                layout.addWidget(field, row, 1)
                self._property_fields[key] = field
                field.textChanged.connect(self.make_field_slot(key, component))
                # NEU: Enter-Handler mit Validierung
                field.returnPressed.connect(self.make_enter_slot(key, component))
                # Beispiel für SpinBox
                if isinstance(field, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
                    field.valueChanged.connect(lambda: self.on_property_field_changed(component))
            row += 1
        # Spacer am Ende
        spacer = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        layout.addItem(spacer, row, 0, 1, 3)

        # IS_ROUND und Variable parameter Signale verbinden
        if "IS_ROUND" in self._property_fields:
            try:
                self._property_fields["IS_ROUND"].stateChanged.disconnect()
            except Exception:
                pass
            self._property_fields["IS_ROUND"].stateChanged.connect(self.update_field_states)

        if "Variable parameter" in self._property_fields:
            try:
                self._property_fields["Variable parameter"].currentIndexChanged.disconnect()
            except Exception:
                pass
            self._property_fields["Variable parameter"].currentIndexChanged.connect(self.update_field_states)

        # --- NEU: Live-Synchronisierung für IS_ROUND (KORRIGIERT) ---
        # Verbinde nur sagittale Felder mit Synchronisierung (nicht beide Richtungen!)
        paired_props = [
        ("Waist radius sagittal", "Waist radius tangential"),
        ("Waist position sagittal", "Waist position tangential"),
        ("Focal length sagittal", "Focal length tangential"),
        ("Radius of curvature sagittal", "Radius of curvature tangential"),
        ("Input radius of curvature sagittal", "Input radius of curvature tangential"),
        ("Output radius of curvature sagittal", "Output radius of curvature tangential"),
        ]

        for sag_key, tan_key in paired_props:
            if sag_key in self._property_fields and tan_key in self._property_fields:
                field_sag = self._property_fields[sag_key]
                field_tan = self._property_fields[tan_key]
                
                def make_sync_function(source_field, target_field):
                    def sync_to_target():
                        # Nur synchronisieren, wenn IS_ROUND aktiv ist
                        if "IS_ROUND" in self._property_fields:
                            is_round_field = self._property_fields["IS_ROUND"]
                            if isinstance(is_round_field, QtWidgets.QCheckBox) and is_round_field.isChecked():
                                target_field.blockSignals(True)
                                target_field.setText(source_field.text())
                                target_field.blockSignals(False)
                    return sync_to_target
                
                # NUR sagittales Feld synchronisiert zum tangentialen (EINSEITIG!)
                field_sag.textChanged.connect(make_sync_function(field_sag, field_tan))

        # Initiale Anwendung
        self.update_field_states()
        self.update_rayleigh()
        
    def update_field_states(self):
        """Zentrale Funktion zur Steuerung aller Feld-Sperrzustände basierend auf IS_ROUND und Variable parameter"""
        # Zustände ermitteln
        is_round = False
        edit_focal_length = True  # Default
        
        is_round_field = self._property_fields.get("IS_ROUND")
        if isinstance(is_round_field, QtWidgets.QCheckBox):
            is_round = is_round_field.isChecked()
            
        var_param_field = self._property_fields.get("Variable parameter")
        if isinstance(var_param_field, QtWidgets.QComboBox):
            edit_focal_length = var_param_field.currentText() == "Edit focal length"
        
        # Prüfe, ob es sich um eine THICK LENS handelt
        is_thick_lens = False
        if hasattr(self, "_last_component_item") and self._last_component_item is not None:
            component = self._last_component_item.data(QtCore.Qt.UserRole)
            if isinstance(component, dict):
                ctype = component.get("type", "").strip().upper()
                is_thick_lens = (ctype == "THICK LENS")
        
        # Die zu prüfenden Feldgruppen
        focal_length_fields = ["Focal length sagittal", "Focal length tangential"]
        curvature_fields = [
            "Radius of curvature sagittal", "Radius of curvature tangential",
            "Input radius of curvature sagittal", "Input radius of curvature tangential",
            "Output radius of curvature sagittal", "Output radius of curvature tangential"
        ]
        
        # 1. Zuerst Felder nach Variable parameter setzen (aber nicht für THICK LENS)
        if not is_thick_lens:
            for key in focal_length_fields:
                field = self._property_fields.get(key)
                if field:
                    if edit_focal_length:
                        field.setReadOnly(False)
                        field.setStyleSheet("")
                    else:
                        field.setReadOnly(True)
                        field.setStyleSheet("background-color: #eee; color: #888;")
            
            for key in curvature_fields:
                field = self._property_fields.get(key)
                if field:
                    if edit_focal_length:
                        field.setReadOnly(True)
                        field.setStyleSheet("background-color: #eee; color: #888;")
                    else:
                        field.setReadOnly(False)
                        field.setStyleSheet("")
        else:
            # Für THICK LENS: Krümmungsradius-Felder immer frei
            for key in curvature_fields:
                field = self._property_fields.get(key)
                if field:
                    field.setReadOnly(False)
                    field.setStyleSheet("")
        
        # 2. IS_ROUND-Logik anwenden (KORRIGIERT)
        paired_props = [
            ("Waist radius sagittal", "Waist radius tangential"),
            ("Waist position sagittal", "Waist position tangential"),
            ("Rayleigh range sagittal", "Rayleigh range tangential"),
            ("Focal length sagittal", "Focal length tangential"),
            ("Radius of curvature sagittal", "Radius of curvature tangential"),
            ("Input radius of curvature sagittal", "Input radius of curvature tangential"),
            ("Output radius of curvature sagittal", "Output radius of curvature tangential"),
        ]
        
        for sag_key, tan_key in paired_props:
            if sag_key in self._property_fields and tan_key in self._property_fields:
                field_sag = self._property_fields[sag_key]
                field_tan = self._property_fields[tan_key]
                
                if is_round:
                    # IS_ROUND = True: Tangential-Feld sperren und synchronisieren
                    field_tan.setReadOnly(True)
                    field_tan.setStyleSheet("background-color: #eee; color: #888;")
                    
                    # Wert synchronisieren
                    if field_tan.text() != field_sag.text():
                        field_tan.blockSignals(True)
                        field_tan.setText(field_sag.text())
                        field_tan.blockSignals(False)
                else:
                    # IS_ROUND = False: Tangential-Feld entsperren (aber nur wenn nicht durch Variable parameter gesperrt)
                    if not is_thick_lens:
                        # Für normale LENS: Prüfe Variable parameter
                        if (tan_key in focal_length_fields and not edit_focal_length) or \
                           (tan_key in curvature_fields and edit_focal_length):
                            # Bleibt gesperrt durch Variable parameter
                            field_tan.setReadOnly(True)
                            field_tan.setStyleSheet("background-color: #eee; color: #888;")
                        else:
                            # Entsperren
                            field_tan.setReadOnly(False)
                            field_tan.setStyleSheet("")
                    else:
                        # Für THICK LENS: Immer entsperren
                        field_tan.setReadOnly(False)
                        field_tan.setStyleSheet("")
        
    def make_field_slot(self, key, component):
        def slot():
            # Alle Properties speichern und zurück in setupList schreiben
            updated_component = self.save_properties_to_component(component)
            if updated_component and hasattr(self, "_last_component_item") and self._last_component_item:
                self._last_component_item.setData(QtCore.Qt.UserRole, updated_component)
        return slot
    
    def make_enter_slot(self, key, component):
        def slot():
            # Alle Properties speichern und zurück in setupList schreiben
            updated_component = self.save_properties_to_component(component)
            if updated_component and hasattr(self, "_last_component_item") and self._last_component_item:
                self._last_component_item.setData(QtCore.Qt.UserRole, updated_component)
            self.update_live_plot_delayed()
        return slot
    
    def make_checkbox_slot(self, key, comp):
        def slot():
            self.save_properties_to_component(comp)
            self.update_live_plot_delayed()
        return slot
    
    def update_rayleigh(self):
        try:
            wavelength = self.vc.convert_to_float(self._property_fields["Wavelength"].text(), self)
            waist_tan = self.vc.convert_to_float(self._property_fields["Waist radius tangential"].text(), self)
            waist_sag = self.vc.convert_to_float(self._property_fields["Waist radius sagittal"].text(), self)
            n = 1
            rayleigh_sag = self.beam.rayleigh_length(wavelength, waist_sag, n)
            rayleigh_tan = self.beam.rayleigh_length(wavelength, waist_tan, n)
            value_str_sag = self.vc.convert_to_nearest_string(rayleigh_sag, self)
            value_str_tan = self.vc.convert_to_nearest_string(rayleigh_tan, self)
            self._property_fields["Rayleigh range sagittal"].setText(value_str_sag)
            self._property_fields["Rayleigh range sagittal"].setReadOnly(True)
            self._property_fields["Rayleigh range sagittal"].setStyleSheet("background-color: #eee; color: #888;")
            self._property_fields["Rayleigh range tangential"].setText(value_str_tan)
            self._property_fields["Rayleigh range tangential"].setReadOnly(True)
            self._property_fields["Rayleigh range tangential"].setStyleSheet("background-color: #eee; color: #888;")
        except KeyError:
            pass
        except Exception:
            self._property_fields["Rayleigh range sagittal"].setText("")
            self._property_fields["Rayleigh range tangential"].setText("")

        self._property_update_timer.timeout.connect(self.update_rayleigh)
        
    def save_properties_to_component(self, component):
        if not component or not hasattr(self, '_property_fields'):
            return component
    
        # Verhindere Updates während Setup-Wechsel
        if hasattr(self, '_switching_setups') and self._switching_setups:
            return component
    
        if self._saving_properties:
            return component
    
        self._saving_properties = True
    
        try:
            updated = copy.deepcopy(component)
            if "properties" not in updated:
                updated["properties"] = {}
            
            for key, field in self._property_fields.items():
                if isinstance(field, QtWidgets.QLineEdit):
                    updated["properties"][key] = self.vc.convert_to_float(field.text())
                elif isinstance(field, QtWidgets.QCheckBox):
                    updated["properties"][key] = field.isChecked()
                elif isinstance(field, QtWidgets.QComboBox):
                    updated["properties"][key] = field.currentText()
                elif isinstance(field, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
                    updated["properties"][key] = field.value()
            
            # Synchronisiere Beam-Properties in der gesamten setupList
            if updated.get("type", "").upper() == "BEAM" and hasattr(self, "setupList"):
                for i in range(self.setupList.count()):
                    item = self.setupList.item(i)
                    comp = item.data(QtCore.Qt.UserRole)
                    if isinstance(comp, dict) and comp.get("type", "").upper() == "BEAM":
                        comp["properties"] = copy.deepcopy(updated["properties"])
                        item.setData(QtCore.Qt.UserRole, comp)
            
            return updated
            
        finally:
            self._saving_properties = False
            
    def _to_bool(self, value):
        """Konvertiert verschiedene Werte zu Boolean."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'on')
        return False

    def _from_bool(self, value):
        """Konvertiert Boolean zu einheitlichem Format."""
        return bool(value)  # Python Boolean
    
    def update_live_plot_delayed(self):
        """Direkter Live-Plot-Update ohne Timer"""
        if self.live_plot_callback:
            self.live_plot_callback()

    def update_rayleigh_delayed(self):
        """Direkter Rayleigh-Update ohne Timer"""
        if hasattr(self, 'update_rayleigh'):
            self.update_rayleigh()

    def on_property_field_changed(self, component):
        updated = self.save_properties_to_component(component)
        if updated and hasattr(self, "_last_component_item") and self._last_component_item:
            self._last_component_item.setData(QtCore.Qt.UserRole, updated)
        self.update_live_plot_delayed()