# Style Guide

Owner decision 2026-10-29. Palette and wear for the facility and the heroes (ASSET_RULES "Textures and
materials", hero workflow v3). Source: the owner's style references
`D:\AI_Labyrinth\Gemini\References\Style\style_01-04.jpg` and the drone's texture
(`Assets/Materials/Drone_Mat_V4/drone_low_M_Drone_AlbedoTransparency.png` + `..._MetallicSmoothness.png`,
the maps M_Drone uses per `ProtectedAssets/DroneBaseline.md`).

**Replaces the 2026-10-04 Cradle starting palette** (warm light-grey paint): the Cradle structure is dark
charcoal paint, the pads ochre (values below).

## Sampled values (median sRGB)
The style images are lit renders: their values are darker than albedo and include shadow. They set hue and
relationships, not albedo.

| Class | style_01 | style_02 | style_03 | style_04 | Note |
|---|---|---|---|---|---|
| dark painted metal (lit) | 44 48 49 | 37 42 45 | 49 52 60 | 39 41 45 | 11-50 % of each image; blue exceeds red by 5-11 |
| lit highlights / steel | 96 104 108 | 91 102 107 | 101 104 111 | 100 101 107 | cool cast again |
| ochre | 130 97 56 | 202 152 77 | 129 101 63 | 247 182 111 | 0.4-0.8 % of the image: accents only |
| cyan emissive | 59 195 207 | 71 223 232 | 93 190 232 | - | hue ~185 deg |
| amber lamps | 221 139 67 | 214 127 66 | 243 160 84 | 217 139 75 | hue ~27 deg, tiny areas |

Drone (M_Drone textures): yellow albedo **159 120 58** (p10 119 86 44, p90 193 148 75), metallic 0,
smoothness 0.54 (p10 0.28, p90 0.75); grey metal parts 111 111 111, metallic 0.82, smoothness 0.40.

## Palette (PBR albedo, sRGB; metallic; smoothness = 1 - roughness)
| Material | Use | Albedo sRGB | Metallic | Smoothness |
|---|---|---|---|---|
| **Charcoal paint** (main) | structure, frames, panels, housings | **60 64 70** (range 52-70, B >= R + 6) | 0 | 0.35-0.50 |
| **Polymer** (secondary) | recesses, channels, bezels, buttons, cable parts | **35 37 39** | 0 | 0.25-0.40 |
| **Machined steel** | rails, rollers, pins, axles, exposed metal at worn edges | **188 190 192** (>= 180) | 1 | 0.55-0.70 |
| **Ochre** | drone-handling parts (cradle pads, service-arm tool head, lever grip), hazard stripes | **159 120 58** (drone median) | 0 | 0.45-0.55 |
| Hazard black | the dark stripes between ochre | 35 37 39 (polymer value) | 0 | 0.35 |
| **Cyan emissive** (main accent) | light strips, ring lights, screens | emission **64 214 230**; off-state albedo 30 45 48 | 0 | 0.6 |
| Amber lamp | small status lamps | emission 240 150 60 | 0 | 0.6 |
| Red | Armed state only (terminal indicators, beacon) | emission 230 35 25 | 0 | 0.6 |

Values follow ASSET_RULES (non-metal albedo 30-240, metal >= 180, metallic 0 or 1 except transitions).
Emission intensity is set in Unity per light role (lighting pass); textures carry the colour.

## Wear (match the drone)
- **Grime**: moderate, in cavities and on lower parts (AO / cavity driven): albedo x0.75-0.85, smoothness
  -0.10. Lighter on vertical faces, heavier near the floor and in recess corners.
- **Edge wear**: on convex edges only (curvature from the bevel bake), 2-6 mm wide, paint chipped to
  machined steel; denser on edges people or machines touch (leaf closing edge, handles, pads).
- **Scratches**: sparse, fine, on large painted faces; no big damage.
- **No rust anywhere** (high-tech facility): no orange streaks, no corrosion, no peeling to brown. Worn
  hazard stripes show the charcoal under-paint, not rust.
- Overall the facility stays darker and cleaner-looking than the drone; the drone's yellow and the cyan
  lights are the brightest things in the room.

## Shapes
Hard-surface language as in the references and the drone: chamfered panels, angled corner cuts, recessed
fields with raised plates, bolted plates, few large forms with small detail in the normal map.
