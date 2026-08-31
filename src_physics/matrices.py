import numpy as np


class Matrices:
    
    def __init__(self):
        pass
    
    def free_space(self, *args):
        """ABCD matrix for propagation through free space with refractive index n"""
        distance, n = args
        return np.array([[1, distance/n], [0, 1]])
    
    def curved_mirror_tangential(self, *args):
        """ABCD matrix for a mirror in the tangential direction"""
        radius_of_curvature, theta = args
        return np.array([[1, 0], [-2 / (radius_of_curvature * np.cos(theta)), 1]])

    def curved_mirror_sagittal(self, *args):
        """ABCD matrix for a mirror in the sagittal direction"""
        radius_of_curvature, theta = args
        return np.array([[1, 0], [(-2 * np.cos(theta)) / radius_of_curvature, 1]])
    
    def lens(self, *args):
        """ABCD matrix for a thin lens"""
        focal_length = args[0]
        return np.array([[1, 0], [-1/focal_length, 1]])
    
    def refraction_curved_interface(self, *args):
        """ABCD matrix for refraction at a curved interface.

        NOTE: This program uses the *reduced* ray convention throughout
        (free space in a medium n is [[1, d/n], [0, 1]]).
        In this convention the refraction matrix is [[1, 0], [(n1-n2)/R, 1]]
        WITHOUT the additional division by n2 (that division belongs to the
        non-reduced convention, where D = n1/n2 and free space is [[1, d], [0, 1]]).
        """
        radius_of_curvature, refractive_index_inital, refractive_index_final = args
        return np.array([[1, 0], [((refractive_index_inital - refractive_index_final) / radius_of_curvature), 1]])
    
    
    def ABCD(self, *args):
        """ABCD matrix for a system of optical elements"""
        A, B, C, D = args
        return np.array([[A, B], [C, D]])

