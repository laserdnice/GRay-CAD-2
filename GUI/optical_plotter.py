import numpy as np
import pyqtgraph as pg
from pyqtgraph import LinearRegionItem
from bisect import bisect_right
from PyQt5.QtWidgets import QMessageBox
from PyQt5 import QtCore

class OpticalSystemPlotter:
    def __init__(self, plot_widget, beam, matrices, vc):
        # Basis-Referenzen
        self.plotWidget = plot_widget
        self.beam = beam
        self.matrices = matrices
        self.vc = vc

        # Plot-Objekte
        self.curve_sag = None
        self.curve_tan = None
        self.vlines = []
        self.z_setup = 0

        # Status
        self._updating_plot = False  # Reentrancy-Schutz

        # Parameter des aktuellen Systems
        self.wavelength = None
        self.waist_sag = None
        self.waist_tan = None
        self.waist_pos_sag = None
        self.waist_pos_tan = None
        self.n = None
        self.optical_system_sag = None
        self.optical_system_tan = None

        # Sichtbare Plot-Daten
        self.z_data = None
        self.w_sag_data = None
        self.w_tan_data = None
        self.z_visible = None

        # Segment-Caches für schnelle q-Abfrage
        self._segments_sag = None
        self._segments_tan = None

        # Globale Profile (vollständiger Systemverlauf)
        self.z_global = None
        self.w_sag_global = None
        self.w_tan_global = None
        self.q_sag_global = None
        self.q_tan_global = None

        # System-Status
        self._system_dirty = True
        self._global_profiles_dirty = True

    # -------------------------
    # Interne Cache-Helfer
    # -------------------------
    def _build_q_segments(self, optical_system, q_initial):
        """Erzeuge Segmentliste für schnelle q-Bestimmung.
        Segment-Dict Felder:
          z_start, z_end, type ('FS'|'EL'), n_medium (bei FS), q_in, q_out
        """
        segments = []
        z_current = 0.0
        q = q_initial
        segments.append({
            'z_start': 0.0,
            'z_end': 0.0,
            'type': 'START',
            'n': None,
            'q_in': q,
            'q_out': q
        })
        for element, params in optical_system:
            # Freiraum
            if hasattr(element, "__func__") and element.__func__ is self.matrices.free_space.__func__:
                length = params[0]
                n_medium = params[1]
                try:
                    length_val = float(length)
                    n_val = float(n_medium)
                except Exception:
                    continue
                if length_val <= 0 or n_val <= 0:
                    continue
                q_in = q
                q_out = q + length_val / n_val  # da ABCD=[1, L/n;0,1]
                seg = {
                    'z_start': z_current,
                    'z_end': z_current + length_val,
                    'type': 'FS',
                    'n': n_val,
                    'q_in': q_in,
                    'q_out': q_out
                }
                segments.append(seg)
                z_current += length_val
                q = q_out
            else:
                # Optisches Element ohne Ausdehnung in z
                if isinstance(params, tuple):
                    ABCD = element(*params)
                else:
                    ABCD = element(params)
                q_in = q
                A, B, C, D = ABCD.flatten()
                q_out = (A * q + B) / (C * q + D)
                seg = {
                    'z_start': z_current,
                    'z_end': z_current,  # kein z-Inkrement
                    'type': 'EL',
                    'n': None,
                    'q_in': q_in,
                    'q_out': q_out
                }
                segments.append(seg)
                q = q_out
        self._system_length = z_current
        # Für schnellen Binär-Suche: separate Liste der z_end Werte
        z_index = [s['z_end'] for s in segments]
        return segments, z_index

    def _ensure_segment_caches(self):
        """Stellt sicher, dass Segment-Caches existieren."""
        if self._segments_sag is None or self._segments_tan is None:
            # Falls noch nicht gebaut (z.B. erster MouseMove vor Plot), versuchen neu zu bauen
            if self.optical_system_sag is not None and self.wavelength is not None:
                q_sag0 = self.beam.q_value(self.waist_pos_sag, self.waist_sag, self.wavelength, self.n)
                q_tan0 = self.beam.q_value(self.waist_pos_tan, self.waist_tan, self.wavelength, self.n)
                self._segments_sag, self._segments_sag_index = self._build_q_segments(self.optical_system_sag, q_sag0)
                self._segments_tan, self._segments_tan_index = self._build_q_segments(self.optical_system_tan, q_tan0)

    def get_q_at(self, z, mode="sagittal"):
        """Schnelle q-Abfrage an Position z mittels Segment-Cache."""
        self._ensure_segment_caches()
        if mode == "sagittal":
            segments = self._segments_sag
            z_index = getattr(self, '_segments_sag_index', [])
        else:
            segments = self._segments_tan
            z_index = getattr(self, '_segments_tan_index', [])
        if not segments:
            return None
        if z <= 0:
            return segments[0]['q_in']
        # Binärsuche nach erstem Segment mit z_end >= z
        pos = bisect_right(z_index, z)
        if pos >= len(segments):
            # hinter letztem Segment -> freie Ausbreitung nach System
            last = segments[-1]
            # freie Ausbreitung: q = q_out + (z - system_length)/n (n≈1 hier)
            return last['q_out'] + (z - last['z_end']) / (self.n if self.n else 1)
        seg = segments[pos]
        if seg['type'] == 'FS':
            # innerhalb Freiraumsegment
            dz = min(max(0.0, z - seg['z_start']), seg['z_end'] - seg['z_start'])
            return seg['q_in'] + dz / seg['n']
        else:
            # Element oder Start -> q_out repräsentiert Zustand NACH Element; bei punktuellen Elementen ist z exakt an z_start==z_end
            return seg['q_out']

    def update_live_plot(self, main_window):
        """Update the live plot based on current setup"""
        if main_window._plot_busy:
            return
        main_window._plot_busy = True
        try:
            # Suche explizit den Beam in der setupList
            beam_item = None
            for i in range(main_window.setupList.count()):
                item = main_window.setupList.item(i)
                comp = item.data(QtCore.Qt.UserRole)
                if isinstance(comp, dict) and comp.get("type", "").upper() == "BEAM":
                    beam_item = item
                    break
            if beam_item is None:
                return  # Kein Beam gefunden

            beam_data = beam_item.data(QtCore.Qt.UserRole)
            if beam_data is None:
                QMessageBox.warning(self, "Error", "No data found in beam item")
                return

            # Properties speichern (wie gehabt)
            if hasattr(main_window, '_property_fields'):
                updated_beam = main_window.save_properties_to_component(beam_data)
                if updated_beam is not None:
                    beam_item.setData(QtCore.Qt.UserRole, updated_beam)
                    beam_data = updated_beam
        
            optical_system_sag = main_window.build_optical_system_from_setup_list(mode="sagittal")
            optical_system_tan = main_window.build_optical_system_from_setup_list(mode="tangential")
            
            # KORRIGIERT: Verwende bereits validierte beam_data
            props = beam_data.get("properties", {})
            wavelength = props.get("Wavelength", 514E-9)
            waist_sag = props.get("Waist radius sagittal", 1E-3)
            waist_tan = props.get("Waist radius tangential", 1E-3)
            waist_pos_sag = props.get("Waist position sagittal", 0.0)
            waist_pos_tan = props.get("Waist position tangential", 0.0)
            n = 1  # Optional: aus Beam-Properties holen
            
            try:
                self.plot_optical_system(
                    z_start_sag=waist_pos_sag,
                    z_start_tan=waist_pos_tan,
                    wavelength=wavelength,
                    waist_sag=waist_sag,
                    waist_tan=waist_tan,
                    n=n,
                    optical_system_sag=optical_system_sag,
                    optical_system_tan=optical_system_tan
                )
            except Exception as e:
                QMessageBox.critical(main_window, "Error", f"Error in plot_optical_system: {e}")
        except Exception as e:
            QMessageBox.critical(main_window, "Error", f"Error in update_live_plot: {e}")
        finally:
            main_window._plot_busy = False

    def plot_optical_system(self, z_start_sag, z_start_tan, wavelength, waist_sag, waist_tan, n, optical_system_sag, optical_system_tan):
        """Plot the optical system with sagittal and tangential beams"""
        # KORRIGIERT: Verhindere Rekursion während Initialisierung
        if self._updating_plot:
            return
        
        self._updating_plot = True
        
        try:
            # Speichere Parameter
            self.wavelength = wavelength
            self.waist_sag = waist_sag
            self.waist_tan = waist_tan
            self.waist_pos_sag = z_start_sag
            self.waist_pos_tan = z_start_tan
            self.n = n
            self.optical_system_sag = optical_system_sag
            self.optical_system_tan = optical_system_tan
            
            self.curve_sag = None
            self.curve_tan = None
            self.plotWidget.clear()

            # ViewBox holen
            vb = self.plotWidget.getViewBox()
            
            # Wenn ein Signal bereits verbunden ist, trenne NUR dieses eine
            try:
                vb.sigXRangeChanged.disconnect(self.update_plot_for_visible_range)
            except (TypeError, RuntimeError):
                # Signal war nicht verbunden, ignorieren
                pass
        
            # Bestimme initialen Bereich aus optischem System
            z_max = sum([p[1][0] for p in optical_system_sag 
                        if hasattr(p[0], "__func__") and p[0].__func__ is self.matrices.free_space.__func__])
            z_min = 0
            
            # Setze ViewBox-Range ohne Signal
            vb.setXRange(z_min, z_max, padding=0.02)
            
            # Segment-Caches vor erster Plot-Berechnung anlegen
            q_sag0 = self.beam.q_value(self.waist_pos_sag, self.waist_sag, self.wavelength, self.n)
            q_tan0 = self.beam.q_value(self.waist_pos_tan, self.waist_tan, self.wavelength, self.n)
            self._segments_sag, self._segments_sag_index = self._build_q_segments(self.optical_system_sag, q_sag0)
            self._segments_tan, self._segments_tan_index = self._build_q_segments(self.optical_system_tan, q_tan0)

            # Globale Profile berechnen (gesamtes System)
            self._build_global_profiles(q_sag0, q_tan0)

            # Initiale Plot-Berechnung (sichtbarer Bereich)
            self._update_plot_internal(z_min, z_max)
            
            # Signal wieder verbinden NACH der Initialisierung
            vb.sigXRangeChanged.connect(self.update_plot_for_visible_range)
            
        finally:
            self._updating_plot = False

    def update_plot_for_visible_range(self, view_box, view_range):
        """Update plot for the currently visible range"""
        # KORRIGIERT: Verhindere Rekursion
        if self._updating_plot:
            return
        
        if not hasattr(self, 'optical_system_sag') or self.optical_system_sag is None:
            return
    
        self._updating_plot = True
    
        try:
            # Aktueller sichtbarer Bereich
            z_min, z_max = view_range
            
            # Begrenze auf positiven Bereich
            z_min = max(0, z_min)
            z_max = max(z_min + 1e-6, z_max)
            
            if not np.isfinite(z_min) or not np.isfinite(z_max):
                return
            
            # Interne Update-Funktion aufrufen
            self._update_plot_internal(z_min, z_max)
            
        finally:
            self._updating_plot = False

    def _update_plot_internal(self, z_min, z_max):
        """Interne Plot-Update-Funktion ohne Signal-Behandlung"""
        FIXED_RESOLUTION = 800  # Sichtbereich-Auflösung
        z_visible = np.linspace(z_min, z_max, FIXED_RESOLUTION)

        try:
            if self.z_global is None:
                # Fallback: falls globale Profile fehlen (sollte nicht passieren)
                w_sag_vals = []
                w_tan_vals = []
                for z in z_visible:
                    qz_sag = self.get_q_at(z, mode="sagittal")
                    qz_tan = self.get_q_at(z, mode="tangential")
                    if qz_sag is None or qz_tan is None:
                        continue
                    w_sag_vals.append(self.beam.beam_radius(qz_sag, self.wavelength, self.n))
                    w_tan_vals.append(self.beam.beam_radius(qz_tan, self.wavelength, self.n))
                self.z_data = z_visible
                self.w_sag_data = np.array(w_sag_vals)
                self.w_tan_data = np.array(w_tan_vals)
            else:
                # Interpolation + analytische Fortsetzung hinter letztem Element
                z0 = self.z_global[0]
                z1 = self.z_global[-1]
                self.z_data = z_visible
                w_sag = np.empty_like(z_visible)
                w_tan = np.empty_like(z_visible)
                q_last_sag = self.q_sag_global[-1]
                q_last_tan = self.q_tan_global[-1]
                # Bereich innerhalb globaler Daten
                inside_mask = (z_visible <= z1) & (z_visible >= z0)
                if inside_mask.any():
                    z_inside = np.clip(z_visible[inside_mask], z0, z1)
                    w_sag[inside_mask] = np.interp(z_inside, self.z_global, self.w_sag_global)
                    w_tan[inside_mask] = np.interp(z_inside, self.z_global, self.w_tan_global)
                # Hinter System: freie Ausbreitung ab q_last
                after_mask = z_visible > z1
                if after_mask.any():
                    dz = z_visible[after_mask] - z1
                    # freie Ausbreitung: q_new = q_last + dz/n
                    q_prop_sag = q_last_sag + dz / (self.n if self.n else 1)
                    q_prop_tan = q_last_tan + dz / (self.n if self.n else 1)
                    w_sag[after_mask] = np.array([self.beam.beam_radius(qv, self.wavelength, self.n) for qv in q_prop_sag])
                    w_tan[after_mask] = np.array([self.beam.beam_radius(qv, self.wavelength, self.n) for qv in q_prop_tan])
                # Vor System (z < 0) theoretisch nicht sichtbar, aber falls doch: konstant erster Wert
                before_mask = z_visible < z0
                if before_mask.any():
                    w_sag[before_mask] = self.w_sag_global[0]
                    w_tan[before_mask] = self.w_tan_global[0]
                self.w_sag_data = w_sag
                self.w_tan_data = w_tan
            self.z_setup = getattr(self, '_system_length', 0)
            
            # Plot aktualisieren oder erstellen
            if hasattr(self, "curve_sag") and self.curve_sag is not None:
                # Nur Daten aktualisieren
                self.curve_sag.setData(self.z_data, self.w_sag_data)
                self.curve_tan.setData(self.z_data, self.w_tan_data)
            else:
                # Initialer Plot
                self._create_initial_plot()
                
        except Exception as e:
            print(f"Error in plot calculation: {e}")

    def _create_initial_plot(self):
        """Erstelle initialen Plot - OHNE ViewBox-Manipulation"""
        self.plotWidget.setBackground('w')
    
        # Legend nur hinzufügen wenn noch nicht vorhanden
        if not hasattr(self.plotWidget, '_legend') or self.plotWidget._legend is None:
            self.plotWidget.addLegend()
        
        self.plotWidget.showGrid(x=True, y=True)
        self.plotWidget.setLabel('left', 'Waist radius', units='m', color='#333333')
        self.plotWidget.setLabel('bottom', 'z', units='m', color='#333333')
        self.plotWidget.setTitle("Gaussian Beam Propagation", color='#333333')
        
        # Setup-Region (OHNE ViewBox-Änderung)
        if hasattr(self, 'z_setup') and self.z_setup > 0:
            region = LinearRegionItem(values=[0, self.z_setup], orientation='vertical', 
                                    brush=(100, 100, 255, 30), movable=False)
            self.plotWidget.addItem(region)
        
        # Kurven erstellen (OHNE Auto-Range)
        if hasattr(self, 'z_data') and hasattr(self, 'w_sag_data') and hasattr(self, 'w_tan_data'):
            self.curve_sag = self.plotWidget.plot(self.z_data, self.w_sag_data, 
                                                pen=pg.mkPen('r', width=1.5), name="Sagittal")
            self.curve_tan = self.plotWidget.plot(self.z_data, self.w_tan_data, 
                                                pen=pg.mkPen('b', width=1.5), name="Tangential")
        
        # Vertikale Linien (mit Fehlerbehandlung)
        try:
            self.update_vertical_lines()
        except Exception as e:
            print(f"Warning: Could not update vertical lines: {e}")

    def scale_visible_setup(self):
        """Scale the visible setup elements to the current view"""
        if self._updating_plot:
            return
        
        self._updating_plot = True
        
        try:
            vb = self.plotWidget.getViewBox()
            
            # EINFACHER: Direkte Range-Setzung ohne Signal-Manipulation
            if hasattr(self, 'z_setup') and self.z_setup > 0:
                # X-Range auf Setup-Bereich setzen
                vb.setXRange(0, self.z_setup, padding=0.02)
                    
                max_w_sag = np.max(self.w_sag_data) if len(self.w_sag_data) > 0 else 0
                max_w_tan = np.max(self.w_tan_data) if len(self.w_tan_data) > 0 else 0
                ymax = max(max_w_sag, max_w_tan)
                if ymax > 0:
                    vb.setYRange(0, ymax * 1.1, padding=0.05)
        
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error in scale_visible_setup: {e}")
        finally:
            self._updating_plot = False

    def plot_optical_system_from_resonator(self, optical_system):
        """Plot optical system from resonator setup"""
        self.plot_optical_system(optical_system=optical_system)

    def update_vertical_lines(self):
        """Update vertical lines for optical elements"""
        # Alte Linien entfernen
        for vline in getattr(self, "vlines", []):
            self.plotWidget.removeItem(vline)
        self.vlines = []
        
        # Neue Linien hinzufügen
        if hasattr(self, 'optical_system_sag') and self.optical_system_sag:
            z_element = 0
            for idx, (element, param) in enumerate(self.optical_system_sag):
                if hasattr(element, "__func__") and element.__func__ is self.matrices.free_space.__func__:
                    # Freiraum-Segment - Position erhöhen
                    z_element += param[0]
                else:
                    # Optisches Element - vertikale Linie zeichnen
                    vline = pg.InfiniteLine(pos=z_element, angle=90, pen=pg.mkPen(width=2, color="#FF0000"))
                    self.plotWidget.addItem(vline)
                    self.vlines.append(vline)

    def get_element_positions(self):
        """Get z-positions of all optical elements"""
        positions = []
        if hasattr(self, 'optical_system_sag') and self.optical_system_sag:
            z_current = 0
            for element, param in self.optical_system_sag:
                if hasattr(element, "__func__") and element.__func__ is self.matrices.free_space.__func__:
                    z_current += param[0]
                else:
                    positions.append(z_current)
        return positions

    def clear_vertical_lines(self):
        """Clear all vertical lines from the plot"""
        for vline in getattr(self, "vlines", []):
            self.plotWidget.removeItem(vline)
        self.vlines = []

    # -------------------------
    # Globale Profil-Berechnung
    # -------------------------
    def _build_global_profiles(self, q_sag0, q_tan0):
        """Berechnet vollständige q- und w-Verläufe entlang des Systems für effizientes Slicing."""
        if self._segments_sag is None or self._segments_tan is None:
            return
        # Ziel: max. Punkte begrenzen (z.B. 5000) proportional zu Segmentlängen
        max_points = 5000
        system_length = getattr(self, '_system_length', 0.0)
        if system_length <= 0:
            # Nur Startpunkt
            self.z_global = np.array([0.0])
            self.q_sag_global = np.array([q_sag0])
            self.q_tan_global = np.array([q_tan0])
            self.w_sag_global = np.array([self.beam.beam_radius(q_sag0, self.wavelength, self.n)])
            self.w_tan_global = np.array([self.beam.beam_radius(q_tan0, self.wavelength, self.n)])
            return
        # Sammle Freiraumsegmente für Verteilung
        free_segments = [s for s in self._segments_sag if s['type'] == 'FS']
        total_free_length = sum((s['z_end'] - s['z_start']) for s in free_segments)
        # Mindestens Punkte an jedem Element/Segment-Übergang
        z_points = set()
        for s in self._segments_sag:
            z_points.add(s['z_start'])
            z_points.add(s['z_end'])
        # Restliche Punkte auf freie Segmente verteilen
        base_points = len(z_points)
        remaining = max(max_points - base_points, 0)
        z_extra = []
        for s in free_segments:
            length = s['z_end'] - s['z_start']
            if length <= 0:
                continue
            share = remaining * (length / total_free_length) if total_free_length > 0 else 0
            pts = int(max(2, share))  # mindestens 2 pro Segment
            local = np.linspace(s['z_start'], s['z_end'], pts)
            z_extra.extend(local.tolist())
        # Kombinieren
        for z in z_extra:
            z_points.add(float(z))
        z_global = np.array(sorted(z_points))
        # q-Profile berechnen durch Cache-Abfrage
        q_sag_list = []
        q_tan_list = []
        w_sag_list = []
        w_tan_list = []
        for z in z_global:
            qs = self.get_q_at(z, mode="sagittal")
            qt = self.get_q_at(z, mode="tangential")
            q_sag_list.append(qs)
            q_tan_list.append(qt)
            w_sag_list.append(self.beam.beam_radius(qs, self.wavelength, self.n))
            w_tan_list.append(self.beam.beam_radius(qt, self.wavelength, self.n))
        self.z_global = z_global
        self.q_sag_global = np.array(q_sag_list, dtype=complex)
        self.q_tan_global = np.array(q_tan_list, dtype=complex)
        self.w_sag_global = np.array(w_sag_list)
        self.w_tan_global = np.array(w_tan_list)

    def mark_system_dirty(self):
        """Extern aufrufbar: erzwingt Neuaufbau des optischen Systems und globaler Profile."""
        self._system_dirty = True
        self._global_profiles_dirty = True
        # Cache-Arrays leeren
        self.z_global = None
        self.w_sag_global = None
        self.w_tan_global = None
        self.q_sag_global = None
        self.q_tan_global = None
        self._segments_sag = None
        self._segments_tan = None