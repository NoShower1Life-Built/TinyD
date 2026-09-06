# TinyD Marketplace

Standalone, dependency-free marketplace UI for the TinyD ecosystem.

## Included

- Package discovery and search
- Category filtering
- Featured package cards
- Rating/newest sorting
- Grid/list presentation
- Responsive layout
- Light/dark presentation toggle
- Publish CTA surface
- Keyboard `/` search shortcut

## Runtime

The app is static HTML/CSS/JavaScript and requires no package installation. Serve `index.html` from any static host or mount the directory behind the TinyD/Nexus AI control plane.

## Product model

Marketplace packages represent versioned TinyD capabilities: agents, deterministic workflows, tools, connectors, and policy packs. Production integration should replace the demo package array in `app.js` with the marketplace API and connect package detail, authentication, billing, installation, verification, and publishing flows to the TinyD control plane.
