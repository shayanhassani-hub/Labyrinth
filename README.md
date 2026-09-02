# Labyrinth VR Game 

A virtual reality interactive environment built in Unity, featuring highly optimized 3D assets, custom URP Shader Graphs, and autonomous drone tracking mechanics. 

This project demonstrates a technical art pipeline: from strict mesh optimization and high-to-low poly baking in Blender and Substance Painter, to rendering and gameplay programming in Unity's Universal Render Pipeline (URP).

<img src="https://github.com/user-attachments/assets/492091a1-8c78-4003-81b6-342feb38b01a" width="800" height="412" alt="Showcase" />

##  Tech Stack
* **Engine:** Unity (Universal Render Pipeline)
* **Programming:** C#
* **3D Modeling & Topology:** Blender
* **Texturing & Baking:** Substance Painter
* **Target Hardware:** VR Headsets

##  Technical Highlights

### 3D Asset Pipeline & Mesh Optimization
* **VR-Optimized Geometry:** Modeled game meshes with a strict budget of 2,114 triangles. Resolved non-planar faces and eliminated N-gons to ensure stable real-time deformation.
* **Topology & UV Layouts:** Matched smoothing groups along hard edges directly to split UV seams, preventing shading artifacts. Utilized exact-shape packing to maximize texel density for critical geometry.
* **High-to-Low Poly Baking:** Executed detail bakes using a "Match by Name" convention, transferring bevels and Boolean cuts cleanly without detail bleeding. 
* **PBR & Channel Packing:** Authored realistic, non-destructive PBR materials featuring edge wear and recessed grime. Packed final textures into a single 2K atlas (Metallic in the Red channel, Smoothness in the Alpha channel) to minimize memory consumption.

### Engine Integration & Performance
* **Single-Batch Draw Call Optimization:** Configured a single URP Lit material across all 14 child meshes. Enabled GPU instancing to maintain high visual fidelity while strictly locking performance to a single draw call.
* **Custom Shader Graphs:** Authored custom URP Shader Graphs to drive dynamic emission logic and procedural pulsing without relying on heavy post-processing.
* **Gameplay Programming:** * Wrote C# scripts for autonomous hover mechanics and vector tracking.
  * Engineered runtime `MaterialPropertyBlock` controls to manipulate emission states dynamically without breaking GPU instancing.
