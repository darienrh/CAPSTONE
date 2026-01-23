#!/usr/bin/env python3
"""detection/__init__.py - Base classes and utilities for detection modules"""


class Problem:
    """
    Standardized problem representation
    """
    
    def __init__(self, problem_type, device, category, severity="medium", **kwargs):
        """
        Initialize a problem
        
        Args:
            problem_type: Type of problem (e.g., 'interface_down', 'as_mismatch')
            device: Device name
            category: Category (interface, eigrp, ospf, etc.)
            severity: Severity level (low, medium, high, critical)
            **kwargs: Additional problem-specific data
        """
        self.type = problem_type
        self.device = device
        self.category = category
        self.severity = severity
        self.data = kwargs
        
        # Standard fields
        self.interface = kwargs.get('interface')
        self.line = kwargs.get('line', '')
        self.message = kwargs.get('message', '')
        self.current = kwargs.get('current')
        self.expected = kwargs.get('expected')
    
    def to_dict(self):
        """
        Convert problem to dictionary
        
        Returns:
            Dict representation of problem
        """
        result = {
            'type': self.type,
            'device': self.device,
            'category': self.category,
            'severity': self.severity
        }
        
        # Add optional fields if present
        if self.interface:
            result['interface'] = self.interface
        if self.line:
            result['line'] = self.line
        if self.message:
            result['message'] = self.message
        if self.current is not None:
            result['current'] = self.current
        if self.expected is not None:
            result['expected'] = self.expected
        
        # Add any additional data
        result.update(self.data)
        
        return result
    
    def __repr__(self):
        return f"Problem(type={self.type}, device={self.device}, severity={self.severity})"
    
    @classmethod
    def from_dict(cls, problem_dict):
        """
        Create Problem instance from dictionary
        
        Args:
            problem_dict: Dictionary with problem data
        
        Returns:
            Problem instance
        """
        problem_type = problem_dict.pop('type', 'unknown')
        device = problem_dict.pop('device', 'unknown')
        category = problem_dict.pop('category', 'general')
        severity = problem_dict.pop('severity', 'medium')
        
        return cls(problem_type, device, category, severity, **problem_dict)


class DetectionModule:
    """
    Base class for detection modules
    """
    
    def __init__(self, name, category):
        """
        Initialize detection module
        
        Args:
            name: Module name
            category: Problem category (interface, eigrp, ospf, etc.)
        """
        self.name = name
        self.category = category
        self.detection_count = 0
        self.enabled = True
    
    def detect(self, device_name, telnet_connection, config_manager=None):
        """
        Detect problems (to be overridden by subclasses)
        
        Args:
            device_name: Name of device
            telnet_connection: Active telnet connection
            config_manager: ConfigManager instance
        
        Returns:
            List of Problem instances
        """
        raise NotImplementedError("Subclasses must implement detect()")
    
    def should_check_device(self, device_name, config_manager=None):
        """
        Determine if this module should check a specific device
        
        Args:
            device_name: Name of device
            config_manager: ConfigManager instance
        
        Returns:
            True if should check, False otherwise
        """
        return True
    
    def enable(self):
        """Enable this detection module"""
        self.enabled = True
    
    def disable(self):
        """Disable this detection module"""
        self.enabled = False
    
    def get_statistics(self):
        """
        Get detection statistics
        
        Returns:
            Dict with statistics
        """
        return {
            'name': self.name,
            'category': self.category,
            'enabled': self.enabled,
            'detections': self.detection_count
        }


def standardize_problem_dict(problem_dict, device_name, category):
    """
    Standardize problem dictionary format (for legacy compatibility)
    
    Args:
        problem_dict: Original problem dict
        device_name: Device name
        category: Problem category
    
    Returns:
        Standardized problem dict
    """
    if not isinstance(problem_dict, dict):
        return problem_dict
    
    # Ensure required fields exist
    if 'type' not in problem_dict:
        problem_dict['type'] = 'unknown'
    
    if 'device' not in problem_dict:
        problem_dict['device'] = device_name
    
    if 'category' not in problem_dict:
        problem_dict['category'] = category
    
    if 'severity' not in problem_dict:
        # Auto-determine severity based on type
        problem_type = problem_dict['type']
        if any(x in problem_type for x in ['mismatch', 'missing', 'down']):
            problem_dict['severity'] = 'high'
        else:
            problem_dict['severity'] = 'medium'
    
    return problem_dict


def convert_legacy_problems(problems, device_name, category):
    """
    Convert legacy problem list to standardized format
    
    Args:
        problems: List of problem dicts (legacy format)
        device_name: Device name
        category: Category
    
    Returns:
        List of standardized problem dicts
    """
    return [standardize_problem_dict(p, device_name, category) for p in problems]