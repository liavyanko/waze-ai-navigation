#!/bin/bash

# Quick redeployment script - just run the app
echo "🚀 Quick redeploy starting..."
source venv/bin/activate && streamlit run app.py
