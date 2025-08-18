from pint import UnitRegistry
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import QTimer
import numpy as np

class ValueConverter:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ureg = UnitRegistry()
        self.ureg.default_format = "~P"  # Kompakte SI-Darstellung
        self._error_timer = QTimer()
        self._error_timer.setSingleShot(True)
        self._error_timer.timeout.connect(self._show_delayed_error)
        self._pending_error = None
        self._pending_parent = None

    def convert_to_float(self, value, parent=None, raise_error=False):
        """
        Konvertiert z. B. '1.2 µm' → 1.2e-6 (in Meter)
        Behandelt auch Infinity-Eingaben
        
        Args:
            value: Der zu konvertierende Wert
            parent: Parent-Widget für Fehlermeldungen (wird ignoriert wenn raise_error=True)
            raise_error: Wenn True, wird bei Fehlern sofort eine Exception geworfen
        """
        # Infinity-Strings direkt behandeln
        if isinstance(value, str):
            value_lower = value.strip().lower()
            if value_lower in ['inf', 'infinity', '+inf', '+infinity']:
                return 1e30
            elif value_lower in ['-inf', '-infinity']:
                return -1e30
            
            # Leere Strings
            if not value_lower.strip():
                return 0.0
    
        try:
            quantity = self.ureg.Quantity(value)
            quantity = quantity.to_base_units()
            result = float(quantity.magnitude)
            
            # Sehr große Werte als 1e30 behandeln
            if abs(result) >= 1e29:
                return 1e30 if result > 0 else -1e30
            
            return result
        except Exception as e:
            if raise_error:
                # Sofortiger Fehler für Enter-basierte Validierung
                raise ValueError(f"Invalid value: {value}. Please enter a valid number with unit (e.g. '3.5 mm', '1.2 µm') or 'Infinity'.")
            else:
                # Stummes Versagen für Live-Updates
                return None

    def convert_to_nearest_string(self, value, parent=None):
        """
        Konvertiert z. B. 0.0000012 (Meter) → '1.2 µm'
        Zeigt sehr große Werte als 'Infinity' an
        """
        # Infinity-Strings direkt behandeln
        if isinstance(value, str):
            value_lower = value.strip().lower()
            if value_lower in ['inf', 'infinity', '+inf', '+infinity']:
                return "Infinity"
            elif value_lower in ['-inf', '-infinity']:
                return "-Infinity"
    
        # Infinity-Behandlung für numerische Werte
        if isinstance(value, (int, float)):
            if abs(value) >= 1e29:
                return "Infinity" if value > 0 else "-Infinity"
            
            # Sehr kleine Werte als Null
            if abs(value) < 1e-15:
                return "0"
            
            # Normale numerische Konvertierung
            try:
                q = value * self.ureg.meter
                q = q.to_compact()
                return f"{q:.3f~#P}"
            except Exception:
                return f"{value:.3f}"
    
        # Fallback für alle anderen Fälle
        return str(value)

    def _show_delayed_error(self):
        if self._pending_error is not None:
            QMessageBox.critical(
                self._pending_parent,
                "Error",
                f"Unknown or invalid value: {self._pending_error}. Please enter a valid number with unit (e.g. '3.5 mm', '1.2 µm') or 'Infinity'."
            )
            self._pending_error = None
            self._pending_parent = None

    def _cancel_error(self):
        self._error_timer.stop()
        self._pending_error = None
        self._pending_parent = None

    def is_infinity_input(self, value):
        """
        Prüft ob eine Eingabe als Infinity interpretiert werden soll
        """
        if isinstance(value, str):
            value_lower = value.strip().lower()
            return value_lower in ['inf', 'infinity', '+inf', '+infinity', '-inf', '-infinity']
        return False

    def is_infinity_value(self, value):
        """
        Prüft ob ein numerischer Wert als Infinity behandelt werden soll
        """
        if isinstance(value, (int, float)):
            return abs(value) >= 1e29
        return False

    def _is_infinity_string(self, value):
        """
        Hilfsfunktion zur Erkennung von Infinity-Strings
        """
        if not isinstance(value, str):
            return False
        
        value_lower = value.strip().lower()
        return value_lower in ['inf', 'infinity', '+inf', '+infinity', '-inf', '-infinity']

    def _convert_infinity_string(self, value):
        """
        Konvertiert Infinity-Strings zu den entsprechenden Darstellungen
        """
        if not isinstance(value, str):
            return None
        
        value_lower = value.strip().lower()
        if value_lower in ['inf', 'infinity', '+inf', '+infinity']:
            return "Infinity"
        elif value_lower in ['-inf', '-infinity']:
            return "-Infinity"
        return None
