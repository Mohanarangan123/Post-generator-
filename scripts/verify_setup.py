"""
Setup verification script for the LinkedIn AI Content Generator.

Checks all required dependencies and configurations for Phase 4 (infographic generation).
Run this before starting the backend to ensure everything is properly configured.
"""
import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


def check_imports():
    """Check all required Python packages are installed."""
    print("Checking Python dependencies...")
    missing = []
    
    try:
        import fastapi
        print("  ✓ FastAPI installed")
    except ImportError:
        missing.append("fastapi")
        print("  ✗ FastAPI missing")
    
    try:
        import sqlalchemy
        print("  ✓ SQLAlchemy installed")
    except ImportError:
        missing.append("SQLAlchemy")
        print("  ✗ SQLAlchemy missing")
    
    try:
        import streamlit
        print("  ✓ Streamlit installed")
    except ImportError:
        missing.append("streamlit")
        print("  ✗ Streamlit missing")
    
    try:
        import httpx
        print("  ✓ httpx installed")
    except ImportError:
        missing.append("httpx")
        print("  ✗ httpx missing")
    
    try:
        from PIL import Image
        print("  ✓ Pillow installed")
    except ImportError:
        missing.append("Pillow")
        print("  ✗ Pillow missing")
    
    try:
        import playwright
        print("  ✓ playwright installed")
    except ImportError:
        missing.append("playwright")
        print("  ✗ playwright missing")
    
    if missing:
        print(f"\n❌ Missing packages: {', '.join(missing)}")
        print("   Run: pip install -r requirements.txt")
        return False
    
    print("✅ All Python dependencies installed\n")
    return True


def check_playwright_browsers():
    """Check if Playwright browsers are installed."""
    print("Checking Playwright browsers...")
    try:
        import playwright.sync_api
        # Try to launch chromium to verify it's installed
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
                browser.close()
                print("  ✓ Chromium browser installed and working")
                print("✅ Playwright setup complete\n")
                return True
            except Exception as e:
                print(f"  ✗ Chromium browser not properly installed: {e}")
                print("   Run: playwright install chromium")
                return False
    except ImportError:
        print("  ✗ playwright not installed")
        return False
    except Exception as e:
        print(f"  ✗ Error checking Playwright: {e}")
        return False


def check_env_file():
    """Check if .env file exists and has required settings."""
    print("Checking environment configuration...")
    env_path = Path(__file__).parent.parent / ".env"
    
    if not env_path.exists():
        print("  ✗ .env file not found")
        print("   Run: copy .env.example .env")
        return False
    
    print("  ✓ .env file exists")
    
    # Check for required IMAGE_ settings
    env_content = env_path.read_text()
    
    has_provider = "IMAGE_PROVIDER=" in env_content
    has_output_dir = "IMAGE_OUTPUT_DIR=" in env_content
    
    if has_provider and has_output_dir:
        print("  ✓ IMAGE_PROVIDER configured")
        print("  ✓ IMAGE_OUTPUT_DIR configured")
        print("✅ Environment configuration complete\n")
        return True
    else:
        print("  ⚠ Missing image generation settings")
        if not has_provider:
            print("    Add: IMAGE_PROVIDER=mock")
        if not has_output_dir:
            print("    Add: IMAGE_OUTPUT_DIR=images")
        return False


def check_output_directory():
    """Check if the output directory for images exists."""
    print("Checking output directory...")
    
    try:
        from app.core.config import get_settings
        settings = get_settings()
        output_dir = Path(settings.image_output_dir)
        
        # Make it absolute if relative
        if not output_dir.is_absolute():
            output_dir = Path(__file__).parent.parent / output_dir
        
        if not output_dir.exists():
            output_dir.mkdir(parents=True, exist_ok=True)
            print(f"  ✓ Created output directory: {output_dir}")
        else:
            print(f"  ✓ Output directory exists: {output_dir}")
        
        # Check if writable
        test_file = output_dir / ".test_write"
        try:
            test_file.write_text("test")
            test_file.unlink()
            print("  ✓ Output directory is writable")
            print("✅ Output directory setup complete\n")
            return True
        except Exception as e:
            print(f"  ✗ Output directory not writable: {e}")
            return False
            
    except Exception as e:
        print(f"  ✗ Error checking output directory: {e}")
        return False


def check_ollama():
    """Check if Ollama is running and accessible."""
    print("Checking Ollama service...")
    try:
        import httpx
        from app.core.config import get_settings
        settings = get_settings()
        
        response = httpx.get(settings.ollama_base_url, timeout=5.0)
        print(f"  ✓ Ollama is running at {settings.ollama_base_url}")
        print(f"  ✓ Using model: {settings.ollama_model}")
        print("✅ Ollama service accessible\n")
        return True
    except Exception as e:
        print(f"  ✗ Ollama not accessible: {e}")
        print("   Make sure Ollama is running")
        return False


def main():
    """Run all verification checks."""
    print("=" * 60)
    print("LinkedIn AI Content Generator - Setup Verification")
    print("=" * 60)
    print()
    
    checks = [
        check_imports(),
        check_playwright_browsers(),
        check_env_file(),
        check_output_directory(),
        check_ollama(),
    ]
    
    print("=" * 60)
    if all(checks):
        print("✅ All checks passed! You're ready to generate infographics.")
        print("\nTo start the application:")
        print("  1. Backend:  cd backend && uvicorn app.main:app --reload")
        print("  2. Frontend: streamlit run frontend/app.py")
        return 0
    else:
        print("❌ Some checks failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
