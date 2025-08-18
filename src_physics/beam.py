import numpy as np
from src_physics.matrices import Matrices
from PyQt5.QtWidgets import QMessageBox
import pyqtgraph as pg
from numba import njit

@njit
def beam_radius_numba(q, wavelength, n):
    return np.sqrt(-wavelength / (np.pi * np.imag(1/q)))

class Beam():
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.matrices = Matrices()

    def q_value(self, z, beam_radius, wavelength, n):
        """
        Calculate the q parameter of a Gaussian beam.

        Parameters:
        w (float): Beam radius.
        wavelength (float): Wavelength of the beam.
        n (float): Refractive index of the medium.

        Returns:
        complex: q parameter of the beam.
        """
        if beam_radius <= 0:
            QMessageBox.critical(None, "Error", "Beam radius must be greater than zero.")
            return None
        zr = (np.pi * beam_radius**2) / (wavelength)
        return - z + (1j * zr)

    def beam_radius(self, q, wavelength, n=1):
        """
        Calculate the beam radius from the q parameter.

        Parameters:
        q (complex): q parameter of the beam.
        wavelength (float): Wavelength of the beam.

        Returns:
        float: Beam radius.
        """
        return np.sqrt(-wavelength / (np.pi * n * np.imag(1/q)))

    def rayleigh_length(self, wavelength, beam_radius, n=1):
        """
        Calculate the Rayleigh length of a beam.

        Parameters:
        wavelength (float): Wavelength of the beam.
        n (float): Refractive index of the medium.

        Returns:
        float: Rayleigh length of the beam.
        """
        return np.imag(self.q_value(0, beam_radius, wavelength, n))

    def radius_of_curvature(self, z, waist, wavelength, n=1):
        """
        Calculate the radius of curvature of a beam.

        Parameters:
        q (complex): q parameter of the beam.
        wavelength (float): Wavelength of the beam.
        n (float): Refractive index of the medium.

        Returns:
        float: Radius of curvature of the beam.
        """
        q = self.q_value(z, waist, wavelength, n)
        if q is None or np.real(q) == 0:
            return np.inf  # Wellenfront ist planar
        return abs(q)**2 / np.real(q)
    
    def radius_of_curvature_system(self, z, q_initial, elements, wavelength, n=1):
        """
        Berechnet den Radius of Curvature an Position z unter Berücksichtigung des gesamten optischen Systems.
        - z: Position im System (z.B. absoluter Abstand vom Start)
        - q_initial: Start-q-Parameter (z.B. am Strahlaustritt)
        - elements: Liste der optischen Elemente [(matrix_func, params), ...]
        - wavelength: Wellenlänge
        - n: Brechungsindex
        """
        # Propagiere q bis zur gewünschten Position z
        q_at_z = self._propagate_q_to_position(q_initial, elements, z, n)
        # Berechne Radius of Curvature aus q
        if q_at_z is None or np.real(q_at_z) == 0:
            return np.inf
        return abs(q_at_z)**2 / np.real(q_at_z)
    
    def propagate_q(self, q_in, ABCD):
        A, B, C, D = ABCD.flatten()
        return (A * q_in + B) / (C * q_in + D)
    
    @staticmethod
    @njit
    def propagate_free_space(q_start, dz, n_steps, wavelength, n):
        q = q_start
        z_positions = np.empty(n_steps + 1, dtype=np.float64)
        w_values = np.empty(n_steps + 1, dtype=np.float64)
        z_total = 0.0
        z_positions[0] = z_total
        w_values[0] = beam_radius_numba(q, wavelength, n)
        for i in range(1, n_steps + 1):
            # ABCD-Matrix für Freiraum
            A, B, C, D = 1, dz/n, 0, 1
            q = (A * q + B) / (C * q + D)
            z_total += dz
            z_positions[i] = z_total
            w_values[i] = beam_radius_numba(q, wavelength, n)
        return q, z_total, z_positions, w_values

    def propagate_through_system(self, wavelength, q_initial, elements, z_array, res, n=1):
        """
        Propagiert nur durch den sichtbaren Bereich mit fester Punktzahl
        """
        lambda_ = wavelength
        
        # Sichtbarer Bereich aus z_array
        z_start = np.min(z_array)
        z_end = np.max(z_array)
        z_range = z_end - z_start
        
        if z_range <= 0:
            return np.array([0]), np.array([self.beam_radius(q_initial, lambda_, n)]), 0
        
        # KORRIGIERT: Begrenze z_start auf 0 (keine negativen Bereiche)
        z_start_limited = max(0, z_start)  # Nicht kleiner als 0
        z_end_limited = max(z_start_limited + 1e-6, z_end)  # Mindestbereich
        
        # FESTE Punktzahl im sichtbaren, positiven Bereich
        FIXED_POINTS = res
        z_visible = np.linspace(z_start_limited, z_end_limited, FIXED_POINTS)

        
        # Rest bleibt gleich
        w_values = []
        z_total_system = 0
        
        for z_pos in z_visible:
            q_at_position = self._propagate_q_to_position(q_initial, elements, z_pos, n)
            w_at_position = self.beam_radius(q_at_position, lambda_, n)
            w_values.append(w_at_position)
        
        # Länge des optischen Systems berechnen
        for element, param in elements:
            if hasattr(element, "__func__") and element.__func__ is self.matrices.free_space.__func__:
                z_total_system += param[0]
    
        return z_visible, np.array(w_values), z_total_system

    def _propagate_q_to_position(self, q_initial, elements, target_z, n=1):
        """
        Propagiert q-Parameter zu einer bestimmten z-Position
        """
        q = q_initial
        z_current = 0.0
        
        for element, param in elements:
            if hasattr(element, "__func__") and element.__func__ is self.matrices.free_space.__func__:
                length = param[0]
                n_medium = param[1]
                
                try:
                    length_val = float(length)
                    n_val = float(n_medium)
                    if length_val <= 0 or n_val <= 0:
                        continue
                except Exception:
                    continue
                
                # Prüfe ob target_z in diesem Segment liegt
                if z_current <= target_z <= z_current + length_val:
                    # Propagiere nur bis target_z
                    distance_to_target = target_z - z_current
                    # ABCD-Matrix für Freiraum bis target_z
                    A, B, C, D = 1, distance_to_target/n_val, 0, 1
                    q = (A * q + B) / (C * q + D)
                    return q
                else:
                    # Propagiere durch komplettes Segment
                    A, B, C, D = 1, length_val/n_val, 0, 1
                    q = (A * q + B) / (C * q + D)
                    z_current += length_val
            else:
                # Optisches Element (ABCD-Matrix)
                if isinstance(param, tuple):
                    ABCD = element(*param)
                else:
                    ABCD = element(param)
                q = self.propagate_q(q, ABCD)
        
        # Falls target_z nach dem optischen System liegt
        if target_z > z_current:
            remaining_distance = target_z - z_current
            A, B, C, D = 1, remaining_distance/n, 0, 1
            q = (A * q + B) / (C * q + D)
        
        return q