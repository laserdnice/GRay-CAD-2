import numpy as np
from src_physics.matrices import Matrices

class BowTie:

    def __init__(self):
        self.matrices = Matrices()
        
    def set_problem_dimension(self):
        self.dimension = 5
        return self.dimension

    def set_roundtrip_direction(self):
         self.l1 = self.l1
         self.lc = self.lc
         self.l3 = self.l3
         self.theta = self.theta
         self.l2 = ((2 * self.l1) + self.lc + self.l3) / (2 * np.cos(2*self.theta))
         """Sets the direction of the roundtrip, only needed for plotting"""
         vars = self.lc/2, self.l1, self.l2, self.l3, self.l2, self.l1, self.lc/2
         return vars
    
    def set_roundtrip_tangential(self, nc, lc, n0, l1, l3, r1_tan, r2_tan, theta):
            """Calculate the roundtrip matrix for the tangential plane"""
            l2 = ((2 * l1) + lc + l3) / (2 * np.cos(2*theta))
            
            m1= self.matrices.free_space(lc / 2, nc)
            m2= self.matrices.free_space(l1, n0)
            m3= self.matrices.curved_mirror_tangential(r1_tan, theta)
            m4= self.matrices.free_space(l2, n0)
            m5= self.matrices.curved_mirror_tangential(r2_tan, theta)
            m6= self.matrices.free_space(l3, n0)
            m7= self.matrices.curved_mirror_tangential(r2_tan, theta)
            m8= self.matrices.free_space(l2, n0)
            m9= self.matrices.curved_mirror_tangential(r1_tan, theta)
            m10= self.matrices.free_space(l1, n0)
            m11= self.matrices.free_space(lc / 2, nc)

            return m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11

    def set_roundtrip_sagittal(self, nc, lc, n0, l1, l3, r1_sag, r2_sag, theta):
        """Calculate the roundtrip matrix for the sagittal plane"""
        l2 = ((2 * l1) + lc + l3) / (2 * np.cos(2*theta))
        
        m1= self.matrices.free_space(lc / 2, nc)
        m2= self.matrices.free_space(l1, n0)
        m3= self.matrices.curved_mirror_sagittal(r1_sag, theta)
        m4= self.matrices.free_space(l2, n0)
        m5= self.matrices.curved_mirror_sagittal(r2_sag, theta)
        m6= self.matrices.free_space(l3, n0)
        m7= self.matrices.curved_mirror_sagittal(r2_sag, theta)
        m8= self.matrices.free_space(l2, n0)
        m9= self.matrices.curved_mirror_sagittal(r1_sag, theta)
        m10= self.matrices.free_space(l1, n0)
        m11= self.matrices.free_space(lc / 2, nc)

        return m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11        

    def set_fitness(self, waist_sag, waist_tan, target_sag, target_tan):
            """Calculate the fitness value for the Bowtie resonator"""
            if waist_sag < waist_tan:
                fitness_value = np.sqrt(
                    2*((waist_sag - target_sag) / target_sag)**2 +  # Double weight for smaller waist
                    ((waist_tan - target_tan) / target_tan)**2
                )
                return fitness_value,
            if waist_sag > waist_tan:
                fitness_value = np.sqrt(
                    ((waist_sag - target_sag) / target_sag)**2 +
                    2*((waist_tan - target_tan) / target_tan)**2    # Double weight for smaller waist
                )
                return fitness_value,

            if waist_sag == waist_tan:
                fitness_value = np.sqrt(
                    ((waist_sag - target_sag) / target_sag)**2 +
                    ((waist_tan - target_tan) / target_tan)**2
                )
                return fitness_value,
            
    def _add_bowtie_components(self, setup_components, wavelength, lc, nc):
        """Fügt BowTie-spezifische Komponenten hinzu"""
        # Kristall erste Hälfte
        if lc > 0:
            setup_components.append({
                "type": "PROPAGATION",
                "name": "Crystal (first half)",
                "properties": {
                    "Length": lc / 2,
                    "Refractive index": nc
                }
            })
        
        # Propagation zu Spiegel 1
        setup_components.append({
            "type": "PROPAGATION",
            "name": "Propagation to Mirror 1",
            "properties": {
                "Length": self.l1,
                "Refractive index": 1.0
            }
        })
        
        # Spiegel 1
        setup_components.append({
            "type": "MIRROR",
            "name": "Mirror 1",
            "properties": {
                "Radius of curvature sagittal": self.r1_sag,
                "Radius of curvature tangential": self.r1_tan,
                "Angle of incidence": self.theta,
                "IS_ROUND": abs(self.r1_sag - self.r1_tan) < 1e-12
            }
        })
        
        # Propagation zu Spiegel 2
        setup_components.append({
            "type": "PROPAGATION",
            "name": "Propagation to Mirror 2", 
            "properties": {
                "Length": self.l2,
                "Refractive index": 1.0
            }
        })
        
        # Spiegel 2
        setup_components.append({
            "type": "MIRROR",
            "name": "Mirror 2",
            "properties": {
                "Radius of curvature sagittal": self.r2_sag,
                "Radius of curvature tangential": self.r2_tan,
                "Angle of incidence": self.theta,
                "IS_ROUND": abs(self.r2_sag - self.r2_tan) < 1e-12
            }
        })
        
        # Propagation zurück
        setup_components.append({
            "type": "PROPAGATION",
            "name": "Propagation back",
            "properties": {
                "Length": self.l3,
                "Refractive index": 1.0
            }
        })
        
        # Spiegel 2 (Rückweg)
        setup_components.append({
            "type": "MIRROR",
            "name": "Mirror 2 (return)",
            "properties": {
                "Radius of curvature sagittal": self.r2_sag,
                "Radius of curvature tangential": self.r2_tan,
                "Angle of incidence": self.theta,
                "IS_ROUND": abs(self.r2_sag - self.r2_tan) < 1e-12
            }
        })
        
        # Propagation zurück zu Spiegel 1
        setup_components.append({
            "type": "PROPAGATION",
            "name": "Propagation back to Mirror 1",
            "properties": {
                "Length": self.l2,
                "Refractive index": 1.0
            }
        })
        
        # Spiegel 1 (Rückweg)
        setup_components.append({
            "type": "MIRROR",
            "name": "Mirror 1 (return)",
            "properties": {
                "Radius of curvature sagittal": self.r1_sag,
                "Radius of curvature tangential": self.r1_tan,
                "Angle of incidence": self.theta,
                "IS_ROUND": abs(self.r1_sag - self.r1_tan) < 1e-12
            }
        })
        
        # Propagation zurück zum Kristall
        setup_components.append({
            "type": "PROPAGATION",
            "name": "Propagation back to crystal",
            "properties": {
                "Length": self.l1,
                "Refractive index": 1.0
            }
        })
        
        # Kristall zweite Hälfte
        if lc > 0:
            setup_components.append({
                "type": "PROPAGATION",
                "name": "Crystal (second half)",
                "properties": {
                    "Length": lc / 2,
                    "Refractive index": nc
                }
            })

class FabryPerot:
     
    def __init__(self):
        self.matrices = Matrices()

    def set_problem_dimension(self):
        self.dimension = 2
        return self.dimension

    def set_roundtrip_direction(self):
         self.l1 = self.l1
         self.lc = self.lc
         """Sets the direction of the roundtrip, only needed for plotting"""
         return self.lc/2, self.l1, self.l1, self.lc, self.l1, self.l1, self.lc/2
    
    def set_roundtrip_tangential(self, nc, lc, n0, l1, r1_tan):
        """Calculate the roundtrip matrix for the tangential plane"""

        m1 = self.matrices.free_space(lc / 2, nc)
        m2 = self.matrices.free_space(l1, n0)
        m3 = self.matrices.curved_mirror_sagittal(r1_tan, 0)
        m4 = self.matrices.free_space(l1, n0)
        m5 = self.matrices.free_space(lc / 2, nc)

        return m1, m2, m3, m4, m5

    def set_roundtrip_sagittal(self, nc, lc, n0, l1, r1_sag):
        """Calculate the roundtrip matrix for the sagittal plane"""
        
        m1 = self.matrices.free_space(lc / 2, nc)
        m2 = self.matrices.free_space(l1, n0)
        m3 = self.matrices.curved_mirror_sagittal(r1_sag, 0)
        m4 = self.matrices.free_space(l1, n0)
        m5 = self.matrices.free_space(lc / 2, nc)

        return m1, m2, m3, m4, m5

    def set_fitness(self, waist_sag, waist_tan, target_sag, target_tan):
            """Calculate the fitness value for the Bowtie resonator"""
            if waist_sag < waist_tan:
                fitness_value = np.sqrt(
                    2*((waist_sag - target_sag) / target_sag)**2 +  # Double weight for smaller waist
                    ((waist_tan - target_tan) / target_tan)**2
                )
                return fitness_value,
            if waist_sag > waist_tan:
                fitness_value = np.sqrt(
                    ((waist_sag - target_sag) / target_sag)**2 +
                    2*((waist_tan - target_tan) / target_tan)**2    # Double weight for smaller waist
                )
                return fitness_value,

            if waist_sag == waist_tan:
                fitness_value = np.sqrt(
                    ((waist_sag - target_sag) / target_sag)**2 +
                    ((waist_tan - target_tan) / target_tan)**2
                )
                return fitness_value,
            
    def _add_fabryperot_components(self, setup_components, wavelength, lc, nc):
        """Fügt FabryPerot-spezifische Komponenten hinzu"""
        # Kristall erste Hälfte
        if lc > 0:
            setup_components.append({
                "type": "PROPAGATION",
                "name": "Crystal (first half)",
                "properties": {
                    "Length": lc / 2,
                    "Refractive index": nc
                }
            })
        
        # Propagation zu Spiegel
        setup_components.append({
            "type": "PROPAGATION",
            "name": "Propagation to End Mirror",
            "properties": {
                "Length": self.l1,
                "Refractive index": 1.0
            }
        })
        
        # End Mirror
        setup_components.append({
            "type": "MIRROR",
            "name": "End Mirror",
            "properties": {
                "Radius of curvature sagittal": self.r1_sag,
                "Radius of curvature tangential": self.r1_tan,
                "Angle of incidence": 0.0,
                "IS_ROUND": abs(self.r1_sag - self.r1_tan) < 1e-12
            }
        })
        
        # Propagation zurück
        setup_components.append({
            "type": "PROPAGATION",
            "name": "Propagation back",
            "properties": {
                "Length": self.l1,
                "Refractive index": 1.0
            }
        })
        
        # Kristall zweite Hälfte
        if lc > 0:
            setup_components.append({
                "type": "PROPAGATION",
                "name": "Crystal (second half)",
                "properties": {
                    "Length": lc / 2,
                    "Refractive index": nc
                }
            })
            
class Triangle:
    
    def __init__(self):
        self.matrices = Matrices()

    def set_problem_dimension(self):
        self.dimension = 4
        return self.dimension

    def set_roundtrip_direction(self):
         self.l1 = self.l1
         self.lc = self.lc
         self.l2 = self.l2
         """Sets the direction of the roundtrip, only needed for plotting"""
         return self.lc/2, self.l1, self.l2, self.l2, self.l1, self.lc/2
    
    def set_roundtrip_tangential(self, nc, lc, n0, l1, r1_tan, r2_tan, theta):
        """Calculate the roundtrip matrix for the tangential plane"""
        phi = (np.pi/2 - 2*theta)
        l2 = (l1 + lc / 2)/np.cos(2 * theta)

        m1 = self.matrices.free_space(lc / 2, nc)
        m2 = self.matrices.free_space(l1, n0)
        m3 = self.matrices.curved_mirror_tangential(r1_tan, theta)
        m4 = self.matrices.free_space(l2, n0)
        m5 = self.matrices.curved_mirror_tangential(r2_tan, phi)
        m6 = self.matrices.free_space(l2, n0)
        m7 = self.matrices.curved_mirror_tangential(r1_tan, theta)
        m8 = self.matrices.free_space(l1, n0)
        m9 = self.matrices.free_space(lc / 2, nc)

        return m1, m2, m3, m4, m5, m6, m7, m8, m9

    def set_roundtrip_sagittal(self, nc, lc, n0, l1, r1_sag, r2_sag, theta):
        """Calculate the roundtrip matrix for the sagittal plane"""
        phi = (np.pi/2 - 2*theta)
        l2 = (l1 + lc / 2)/np.cos(2 * theta)

        m1 = self.matrices.free_space(lc / 2, nc)
        m2 = self.matrices.free_space(l1, n0)
        m3 = self.matrices.curved_mirror_sagittal(r1_sag, theta)
        m4 = self.matrices.free_space(l2, n0)
        m5 = self.matrices.curved_mirror_sagittal(r2_sag, phi)
        m6 = self.matrices.free_space(l2, n0)
        m7 = self.matrices.curved_mirror_sagittal(r1_sag, theta)
        m8 = self.matrices.free_space(l1, n0)
        m9 = self.matrices.free_space(lc / 2, nc)
        
        return m1, m2, m3, m4, m5, m6, m7, m8, m9

    def set_fitness(self, waist_sag, waist_tan, target_sag, target_tan):
            """Calculate the fitness value for the Bowtie resonator"""
            if waist_sag < waist_tan:
                fitness_value = np.sqrt(
                    2*((waist_sag - target_sag) / target_sag)**2 +  # Double weight for smaller waist
                    ((waist_tan - target_tan) / target_tan)**2
                )
                return fitness_value,
            if waist_sag > waist_tan:
                fitness_value = np.sqrt(
                    ((waist_sag - target_sag) / target_sag)**2 +
                    2*((waist_tan - target_tan) / target_tan)**2    # Double weight for smaller waist
                )
                return fitness_value,

            if waist_sag == waist_tan:
                fitness_value = np.sqrt(
                    ((waist_sag - target_sag) / target_sag)**2 +
                    ((waist_tan - target_tan) / target_tan)**2
                )
                return fitness_value,
            
    def _add_triangle_components(self, setup_components, wavelength, lc, nc):
        """Fügt Triangle-spezifische Komponenten hinzu"""
        self.phi = (np.pi/2 - 2*self.theta)
        self.l2 = (self.l1 + lc/2)/np.cos(2*self.theta)
        if lc > 0:
            setup_components.append({
                "type": "PROPAGATION",
                "name": "Crystal (first half)",
                "properties": {
                    "Length": lc / 2,
                    "Refractive index": nc
                }
            })
        
        # Propagation zu Spiegel 1
        setup_components.append({
            "type": "PROPAGATION",
            "name": "Propagation to Mirror 1",
            "properties": {
                "Length": self.l1,
                "Refractive index": 1.0
            }
        })
        
        # Spiegel 1
        setup_components.append({
            "type": "MIRROR",
            "name": "Mirror 1",
            "properties": {
                "Radius of curvature sagittal": self.r1_sag,
                "Radius of curvature tangential": self.r1_tan,
                "Angle of incidence": self.theta,
                "IS_ROUND": abs(self.r1_sag - self.r1_tan) < 1e-12
            }
        })
        
        # Propagation zu Spiegel 2
        setup_components.append({
            "type": "PROPAGATION",
            "name": "Propagation to Mirror 2", 
            "properties": {
                "Length": self.l2,
                "Refractive index": 1.0
            }
        })
        
        # Spiegel 2
        setup_components.append({
            "type": "MIRROR",
            "name": "Mirror 2",
            "properties": {
                "Radius of curvature sagittal": self.r2_sag,
                "Radius of curvature tangential": self.r2_tan,
                "Angle of incidence": self.phi,
                "IS_ROUND": abs(self.r2_sag - self.r2_tan) < 1e-12
            }
        })
        
        # Propagation zurück
        setup_components.append({
            "type": "PROPAGATION",
            "name": "Propagation back to Mirror 1",
            "properties": {
                "Length": self.l2,
                "Refractive index": 1.0
            }
        })
        
        # Spiegel 1 (Rückweg)
        setup_components.append({
            "type": "MIRROR",
            "name": "Mirror 1 (return)",
            "properties": {
                "Radius of curvature sagittal": self.r1_sag,
                "Radius of curvature tangential": self.r1_tan,
                "Angle of incidence": self.theta,
                "IS_ROUND": abs(self.r1_sag - self.r1_tan) < 1e-12
            }
        })
        
        # Propagation zurück zum Kristall
        setup_components.append({
            "type": "PROPAGATION",
            "name": "Propagation back to crystal",
            "properties": {
                "Length": self.l1,
                "Refractive index": 1.0
            }
        })
        
        # Kristall zweite Hälfte
        if lc > 0:
            setup_components.append({
                "type": "PROPAGATION",
                "name": "Crystal (second half)",
                "properties": {
                    "Length": lc / 2,
                    "Refractive index": nc
                }
            })
            
class Rectangle:
    
    def __init__(self):
        self.matrices = Matrices()

    def set_problem_dimension(self):
        self.dimension = 4
        return self.dimension

    def set_roundtrip_direction(self):
         self.l1 = self.l1
         self.lc = self.lc
         self.l2 = self.l2
         self.l3 = (2 * self.l1) + self.lc
         """Sets the direction of the roundtrip, only needed for plotting"""
         return self.lc/2, self.l1, self.l2, self.l3, self.l2, self.l1, self.lc/2
    
    def set_roundtrip_tangential(self, nc, lc, n0, l1, l2, r1_tan, r2_tan):
            """Calculate the roundtrip matrix for the tangential plane"""
            l3 = (2 * l1) + lc
            
            m1= self.matrices.free_space(lc / 2, nc)
            m2= self.matrices.free_space(l1, n0)
            m3= self.matrices.curved_mirror_tangential(r1_tan, np.pi/4)
            m4= self.matrices.free_space(l2, n0)
            m5= self.matrices.curved_mirror_tangential(r2_tan, np.pi/4)
            m6= self.matrices.free_space(l3, n0)
            m7= self.matrices.curved_mirror_tangential(r2_tan, np.pi/4)
            m8= self.matrices.free_space(l2, n0)
            m9= self.matrices.curved_mirror_tangential(r1_tan, np.pi/4)
            m10= self.matrices.free_space(l1, n0)
            m11= self.matrices.free_space(lc / 2, nc)

            return m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11

    def set_roundtrip_sagittal(self, nc, lc, n0, l1, l2, r1_sag, r2_sag):
        """Calculate the roundtrip matrix for the sagittal plane"""
        l3 = (2 * l1) + lc
                   
        m1= self.matrices.free_space(lc / 2, nc)
        m2= self.matrices.free_space(l1, n0)
        m3= self.matrices.curved_mirror_sagittal(r1_sag, np.pi/4)
        m4= self.matrices.free_space(l2, n0)
        m5= self.matrices.curved_mirror_sagittal(r2_sag, np.pi/4)
        m6= self.matrices.free_space(l3, n0)
        m7= self.matrices.curved_mirror_sagittal(r2_sag, np.pi/4)
        m8= self.matrices.free_space(l2, n0)
        m9= self.matrices.curved_mirror_sagittal(r1_sag, np.pi/4)
        m10= self.matrices.free_space(l1, n0)
        m11= self.matrices.free_space(lc / 2, nc)

        return m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11     

    def set_fitness(self, waist_sag, waist_tan, target_sag, target_tan):
            """Calculate the fitness value for the Bowtie resonator"""
            if waist_sag < waist_tan:
                fitness_value = np.sqrt(
                    2*((waist_sag - target_sag) / target_sag)**2 +  # Double weight for smaller waist
                    ((waist_tan - target_tan) / target_tan)**2
                )
                return fitness_value,
            if waist_sag > waist_tan:
                fitness_value = np.sqrt(
                    ((waist_sag - target_sag) / target_sag)**2 +
                    2*((waist_tan - target_tan) / target_tan)**2    # Double weight for smaller waist
                )
                return fitness_value,

            if waist_sag == waist_tan:
                fitness_value = np.sqrt(
                    ((waist_sag - target_sag) / target_sag)**2 +
                    ((waist_tan - target_tan) / target_tan)**2
                )
                return fitness_value,
            
    def _add_rectangle_components(self, setup_components, wavelength, lc, nc):
        """Fügt Rectangle-spezifische Komponenten hinzu"""
        self.l3 = (2 * self.l1) + lc
        self.theta = np.pi / 4
        if lc > 0:
            setup_components.append({
                "type": "PROPAGATION",
                "name": "Crystal (first half)",
                "properties": {
                    "Length": lc / 2,
                    "Refractive index": nc
                }
            })
        
        # Propagation zu Spiegel 1
        setup_components.append({
            "type": "PROPAGATION",
            "name": "Propagation to Mirror 1",
            "properties": {
                "Length": self.l1,
                "Refractive index": 1.0
            }
        })
        
        # Spiegel 1
        setup_components.append({
            "type": "MIRROR",
            "name": "Mirror 1",
            "properties": {
                "Radius of curvature sagittal": self.r1_sag,
                "Radius of curvature tangential": self.r1_tan,
                "Angle of incidence": self.theta,
                "IS_ROUND": abs(self.r1_sag - self.r1_tan) < 1e-12
            }
        })
        
        # Propagation zu Spiegel 2
        setup_components.append({
            "type": "PROPAGATION",
            "name": "Propagation to Mirror 2", 
            "properties": {
                "Length": self.l2,
                "Refractive index": 1.0
            }
        })
        
        # Spiegel 2
        setup_components.append({
            "type": "MIRROR",
            "name": "Mirror 2",
            "properties": {
                "Radius of curvature sagittal": self.r2_sag,
                "Radius of curvature tangential": self.r2_tan,
                "Angle of incidence": self.theta,
                "IS_ROUND": abs(self.r2_sag - self.r2_tan) < 1e-12
            }
        })
        
        # Propagation zurück
        setup_components.append({
            "type": "PROPAGATION",
            "name": "Propagation back",
            "properties": {
                "Length": self.l3,
                "Refractive index": 1.0
            }
        })
        
        # Spiegel 2 (Rückweg)
        setup_components.append({
            "type": "MIRROR",
            "name": "Mirror 2 (return)",
            "properties": {
                "Radius of curvature sagittal": self.r2_sag,
                "Radius of curvature tangential": self.r2_tan,
                "Angle of incidence": self.theta,
                "IS_ROUND": abs(self.r2_sag - self.r2_tan) < 1e-12
            }
        })
        
        # Propagation zurück zu Spiegel 1
        setup_components.append({
            "type": "PROPAGATION",
            "name": "Propagation back to Mirror 1",
            "properties": {
                "Length": self.l2,
                "Refractive index": 1.0
            }
        })
        
        # Spiegel 1 (Rückweg)
        setup_components.append({
            "type": "MIRROR",
            "name": "Mirror 1 (return)",
            "properties": {
                "Radius of curvature sagittal": self.r1_sag,
                "Radius of curvature tangential": self.r1_tan,
                "Angle of incidence": self.theta,
                "IS_ROUND": abs(self.r1_sag - self.r1_tan) < 1e-12
            }
        })
        
        # Propagation zurück zum Kristall
        setup_components.append({
            "type": "PROPAGATION",
            "name": "Propagation back to crystal",
            "properties": {
                "Length": self.l1,
                "Refractive index": 1.0
            }
        })
        
        # Kristall zweite Hälfte
        if lc > 0:
            setup_components.append({
                "type": "PROPAGATION",
                "name": "Crystal (second half)",
                "properties": {
                    "Length": lc / 2,
                    "Refractive index": nc
                }
            })