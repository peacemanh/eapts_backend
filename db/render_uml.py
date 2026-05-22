from plantuml import PlantUML

# Use public PlantUML server
server = PlantUML(url='http://www.plantuml.com/plantuml/img/')

# Render diagram
uml_file = "DataElementMetadataModel.uml"
print(f"Generating UML diagram from {uml_file}...")

server.processes_file(uml_file)

print("✅ Diagram generated successfully!")
