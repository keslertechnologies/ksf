[![GitLab](https://img.shields.io/badge/GitLab-FC6D26?logo=gitlab&logoColor=white)](https://gitlab.com/keslers/ksf)
[![GitHub](https://img.shields.io/badge/GitHub-181717?logo=github&logoColor=white)](https://github.com/keslertechnologies/ksf)
[![npm version](https://img.shields.io/npm/v/@keslers/ksf.svg)](https://www.npmjs.com/package/@keslers/ksf)
[![npm downloads](https://img.shields.io/npm/dm/@keslers/ksf.svg)](https://www.npmjs.com/package/@keslers/ksf)
[![license](https://img.shields.io/npm/l/@keslers/ksf)](https://www.npmjs.com/package/@keslers/ksf)

<img src="https://gitlab.com/keslers/ksf/-/raw/main/ksf.png" alt="KSF" width="200" />

# @keslers/ksf — Keslers Sans Font

A heavy, geometric, double-struck display typeface drawn from the Keslers logo lettering.

![KSF specimen](https://gitlab.com/keslers/ksf/-/raw/main/documentation/specimen.png)

- Capitals only: lowercase input renders as capitals
- Hollow double-struck stems, crescent inlines on rounds, and a stemless Ξ-style E
- A–Z, 0–9, and common punctuation and symbols
- OTF, TTF, and WOFF2

## Installation

### Web (npm)

```bash
npm install @keslers/ksf
```

### Web (CDN)

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@keslers/ksf@1/styles.css" />
```

`@1` follows the latest `1.x` release. Pin an exact version (e.g. `@1.0.0`) to never change.

### Desktop

Download [`KSF.otf`](https://gitlab.com/keslers/ksf/-/raw/main/fonts/otf/KSF.otf) and double-click it to install (macOS / Windows), or use [`KSF.ttf`](https://gitlab.com/keslers/ksf/-/raw/main/fonts/ttf/KSF.ttf) for apps that need TrueType.

## Usage

Import the stylesheet once in your entry file:

```tsx
import "@keslers/ksf/styles.css";
```

Then use the `KSF` font family:

```css
h1 {
  font-family: "KSF", sans-serif;
}
```

The raw font files are also exported if you want to write your own `@font-face`:

```css
@font-face {
  font-family: "KSF";
  src: url("@keslers/ksf/fonts/webfonts/KSF.woff2") format("woff2");
}
```

## Development

The font is generated from code. Every glyph is built from geometric primitives in [`sources/build_ksf.py`](sources/build_ksf.py), using the design reference images in [`sources/reference/`](sources/reference/).

```bash
git clone https://gitlab.com/keslers/ksf.git
cd ksf
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python sources/build_ksf.py
```

This writes the fonts to `fonts/`, the specimen to `documentation/specimen.png`, and the `ksf.png` logo. The font version is read from `package.json`, so bump it with `npm version` before rebuilding.

## License

SIL Open Font License 1.1 — see [OFL.txt](OFL.txt)
