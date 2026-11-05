# 🛡️ Aegis - Intelligent File Architecture Agent

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![CustomTkinter](https://img.shields.io/badge/GUI-CustomTkinter-darkgreen)
![Gemini AI](https://img.shields.io/badge/AI-Google_Gemini_Flash-orange)
![License](https://img.shields.io/badge/License-MIT-purple.svg)

**Aegis** is a modern, professional-grade desktop application that intelligently organizes messy folders. It uses a hybrid naming engine combining lightning-fast local heuristics with Google's Gemini 2.5 Flash Vision AI to understand context, extract metadata, and restructure your files safely.

*Replace this text with a screenshot of your app running* 
`![Aegis Screenshot](link-to-your-image.png)`

## ✨ Key Features

* **🧠 Hybrid Intelligence Engine:** 
  * **Fast Smart (Offline):** Uses RegEx and Windows Alternate Data Streams (`Zone.Identifier`) to instantly cluster files by web origin and download time.
  * **Gemini AI (Online):** Reads PDFs, Word docs, and processes screenshots using multimodal vision to generate highly accurate semantic folder names.
* **🛡️ Absolute Safety:** 100% preservation of file metadata (Creation/Modification times). Zero automated deletions.
* **⏪ Time-Travel Undo:** A robust JSON-based history ledger allows you to instantly revert any organization run back to its exact original state.
* **🎨 Modern Fluent UI:** Built with `customtkinter`, featuring automatic Light/Dark mode, WinUI 3 typography, interactive hover tooltips, and non-blocking background threading.
* **📊 Dashboard & History:** Track total files organized, view real-time workspace stats, and audit past operations.

## 🚀 Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/yourusername/aegis-organizer.git](https://github.com/yourusername/aegis-organizer.git)
   cd aegis-organizer