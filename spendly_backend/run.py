"""Start the development server:  python run.py"""
import os
from spendly import create_app

app = create_app()

if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
