"""Quick test for ProjectAnalyzer integration."""
from src.engine.project_analyzer import ProjectAnalyzer
from src.engine.dag_parser import DAGParser

# Test with Electron app requirements
test_req = {
    'project_name': 'MyElectronApp',
    'description': 'A desktop app with Electron and React',
    'features': [
        {'name': 'Main Window', 'details': 'Create BrowserWindow'},
        {'name': 'IPC Communication', 'details': 'ipcMain handlers'},
        {'name': 'React UI', 'details': 'React components in renderer'}
    ]
}

# Parse like the pipeline does
parser = DAGParser()
req_data = parser.parse(test_req)

analyzer = ProjectAnalyzer()
profile = analyzer.analyze(req_data)

print(f'Project Type: {profile.project_type.value}')
print(f'Technologies: {[t.value for t in profile.technologies]}')
print(f'Domains: {[d.value for d in profile.domains]}')
print(f'Agent Types: {profile.get_agent_types()}')
print(f'Validators: {profile.get_validators()}')
