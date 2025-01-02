# IRIS Draw

IRIS Draw is a desktop application for working with facility maps and managing impact zones for various types of objects. The application allows for creation, visualization, and analysis of different object types and their impact zones on facility plans.

## Features

### Database Operations
- Create new SQLite databases
- Connect to existing databases 
- Database optimization (VACUUM)

### Plan Management
- Add new facility plans (supports JPG format)
- Select and load existing plans
- Replace plans while preserving objects
- Clear plans
- Save plans as JPG files
- Delete plans with associated objects

### Object Management
- Support for three object types:
  - Point objects
  - Linear objects
  - Stationary objects
- Add objects with custom parameters (R1-R6 values)
- Edit object coordinates
- Delete objects
- Real-time object highlighting and visualization

### Impact Zone Analysis
- Visualize impact zones for:
  - Individual objects
  - All objects simultaneously
  - Risk assessment visualization
- Scale measurement and calibration tools
- Length and area measurement tools

### Interface Features
- Intuitive graphical interface
- Interactive map navigation
- Pan and zoom functionality
- Object selection and highlighting
- Status bar with helpful information

## Technical Details

### Dependencies
- PySide6 (Qt for Python)
- NumPy
- Shapely
- SQLite3

### Database Structure
- Images table for storing facility plans
- Objects table for storing object data
- Coordinates table for storing object coordinates
- Support for foreign key relationships

### File Support
- Image formats: JPG, JPEG
- Database format: SQLite (.db)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/iris-draw.git
```

2. Install required dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python main.py
```

## Usage Guide

### Basic Workflow
1. Create or connect to a database
2. Add or select a facility plan
3. Set the scale using the scale measurement tool
4. Add objects to the plan
5. Analyze impact zones and risks

### Adding Objects
1. Select the object type from the "Objects" menu
2. Click on the plan to place points
3. Double-click to finish drawing
4. Enter object name and parameters

### Measuring Tools
1. Select the measurement tool (length or area)
2. Click points on the plan
3. Double-click to complete measurement

### Impact Zone Analysis
1. Select an object in the table
2. Choose the desired analysis type from the menu
3. View the visualization on the plan

## Project Structure

```
IRIS_0/
├── main.py                      # Main application entry point
├── main_ico.png                 # Application icon
├── requirements.txt             # Project dependencies
├── draw_zone/                   # Impact zone analysis
│   ├── __init__.py
│   ├── all_impact_zones.py
│   ├── example_heatmap.py
│   ├── impact_zones.py
│   ├── linear_impact_zones.py
│   ├── risk_zones.py
│   └── stationary_impact_zones.py
├── ico/                         # Application icons
├── iris_db/                     # Database components
│   ├── __init__.py
│   ├── database.py
│   ├── models.py
│   ├── repositories.py
│   ├── schema.mermaid
│   └── schema.py
└── service/                     # Core services
    ├── __init__.py
    ├── database_handler.py
    ├── edit_coordinates_manager.py
    ├── measurement_tools.py
    ├── object_items.py
    ├── object_manager.py
    ├── object_table.py
    ├── plan_dialog.py
    └── temp_drawing.py
```

## Contributing

Contributions are welcome! Please feel free to submit pull requests or create issues for bugs and feature requests.

## License

GNU General Public License (GPL)

## Authors

Kuznetsov Konstantin.
email: kuznetsovkm@yandex.ru
