"""
ReveaceSpline — Main entry point
Usage: python -m reveace_pyside6
"""

import sys
import os

# Add the package directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    from PySide6.QtWidgets import QApplication
    from reveace_pyside6.core import ReveaceCore
    
    app = QApplication(sys.argv)
    app.setApplicationName("Reveace Spline")
    app.setStyle("Fusion")
    
    core = ReveaceCore()
    
    from reveace_pyside6.gui_compact import ReveaceWindowCompact
    window = ReveaceWindowCompact(core)
    
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
