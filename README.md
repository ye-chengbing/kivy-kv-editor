# <p align="center"> <img width="256" height="256" alt="kivy-kv-editor" src="https://github.com/user-attachments/assets/dc9cb736-906c-4818-be96-cff7d6312904" /> </p> <div align="center">A drag-and-drop visual editor for Kivy KV language.<br>Built with Python. Actively maintained.</div>

<table align="center">
<tr>
<td valign="top">

## Features

- Drag and drop widgets onto the canvas
- Edit properties like text, width, and height
- Generate and copy KV code to your clipboard
- Lightweight and easy to run

</td>
<td valign="top">
  <img src="https://github.com/user-attachments/assets/152e05d3-f2d4-4e81-ad09-7ac90f3f4f7c" alt="Demo"/>
</td>
</tr>
</table>

## Quick Start

### Windows

1. Install Python 3.x from [python.org](https://www.python.org/) and make sure to check **"Add Python to PATH"** during installation.
2. Download or clone this repository.
3. Open a terminal (cmd) in the project directory.
4. Install Kivy:
```bash
pip install kivy
```
5. Run the editor:
```bash
python main.py
```

### Linux

1. Install Python 3.x.
2. Open a terminal in the project directory.
3. (Optional but recommended) Create a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
```
4. Install Kivy:
```bash
pip install kivy
```
5. Run the editor:
```bash
python main.py
```

### macOS

I don't own a Mac, so I haven't tested it yet. It should work if you install Python 3.x and Kivy. If you try it, feel free to open an issue or PR with your results!

## How to Use

### Create and edit widgets

1. Select the widget you want from the left panel.
2. Long-press and drag it to the preview area in the middle.
3. Modify the display text and width/height in the top-right corner.  
   *Note: You need to press Enter to apply each property change.*

### Copy KV code

Click the button in the bottom-right corner. The generated KV code will be copied to your clipboard.

## Contributing

This project is still active and I'm improving it. If you're interested, give it a star or open an issue — it means a lot to me.
<p align="center"> <img alt="© 2026 ye-chengbing · MIT License" src="https://github.com/user-attachments/assets/8a2672ba-bb80-4483-9ae8-cc088b6f9c00" /> </p>
