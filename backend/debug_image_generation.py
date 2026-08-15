"""
Debug script to verify which model is being used for image generation.
This will show you the exact flow when generating an infographic.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import get_settings
from app.services.image_providers import get_image_provider

def debug_image_generation():
    """Show which models are configured for each step."""
    settings = get_settings()
    
    print("\n" + "=" * 70)
    print("IMAGE GENERATION PIPELINE DEBUG")
    print("=" * 70)
    
    print("\n📋 STEP 1: VisualSpec Generation (Content Structure)")
    print("-" * 70)
    print(f"Model: {settings.ollama_model}")
    print(f"Endpoint: {settings.ollama_base_url}")
    print(f"Purpose: Generate JSON structure for infographic content")
    print(f"✅ This SHOULD use qwen2.5:3b (or similar Ollama model)")
    
    print("\n🎨 STEP 2: Image Generation (Visual Creation)")
    print("-" * 70)
    print(f"Provider: {settings.image_provider}")
    
    if settings.image_provider.lower() in ["huggingface", "hf"]:
        print(f"Model: {settings.hf_image_model}")
        print(f"Inference Provider: {settings.hf_inference_provider}")
        print(f"Token Status: {'✅ Set' if settings.hf_token else '❌ Missing'}")
        print(f"Purpose: Generate complete professional infographic PNG")
        print(f"✅ This SHOULD use Qwen/Qwen-Image-2512")
        
        # Test provider creation
        print("\n🔧 Provider Test:")
        try:
            provider = get_image_provider(settings)
            provider_name = type(provider).__name__
            print(f"✅ Provider created: {provider_name}")
            
            if provider_name == "HuggingFaceImageProvider":
                print(f"   Model ID: {provider._model_id}")
                print(f"   Inference Provider: {provider._provider}")
                print(f"   Token: {provider._token[:15]}..." if provider._token else "   Token: Not set")
            elif provider_name == "MockImageProvider":
                print("   ⚠️  WARNING: Using MockImageProvider (local fallback)")
                print("   This means HuggingFace provider failed to initialize")
                
        except Exception as e:
            print(f"❌ Error creating provider: {e}")
            
    elif settings.image_provider.lower() == "mock":
        print(f"Model: MockImageProvider (local, deterministic)")
        print(f"Purpose: Generate abstract infographic for testing")
        print(f"ℹ️  This is for TESTING only")
        
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    print("\nThe pipeline uses TWO different models:")
    print(f"1. Content Structure: {settings.ollama_model} via Ollama")
    print(f"2. Image Generation: ", end="")
    
    if settings.image_provider.lower() in ["huggingface", "hf"]:
        print(f"{settings.hf_image_model} via HuggingFace")
        if settings.hf_token:
            print("\n✅ CORRECT: Will use Qwen/Qwen-Image-2512 for images")
        else:
            print("\n⚠️  WARNING: HF_TOKEN missing, will fall back to MockImageProvider")
    else:
        print(f"MockImageProvider (local testing)")
        print("\nℹ️  To use Qwen/Qwen-Image-2512:")
        print("   1. Set IMAGE_PROVIDER=huggingface in .env")
        print("   2. Add HF_TOKEN=your_token in .env")
        print("   3. Restart backend")
    
    print("\n" + "=" * 70)
    print("\n")

if __name__ == "__main__":
    try:
        debug_image_generation()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure you're running this from the backend directory:")
        print("  cd backend")
        print("  python debug_image_generation.py")
        sys.exit(1)
