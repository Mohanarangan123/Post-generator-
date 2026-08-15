"""
Quick configuration checker for Phase 4.

Run this to verify your Phase 4 setup is correct.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import get_settings

def check_config():
    """Check Phase 4 configuration and print status."""
    settings = get_settings()
    
    print("\n" + "=" * 60)
    print("PHASE 4 CONFIGURATION CHECK")
    print("=" * 60)
    
    # Image Provider
    provider = settings.image_provider.lower()
    print(f"\n📦 Image Provider: {settings.image_provider}")
    
    if provider in ["mock", "svg", "local_svg", "local"]:
        print("   ✅ Using local mock provider (no API key needed)")
        print("   ℹ️  Generates deterministic abstract infographics")
        print("   ℹ️  Good for: Testing, development, offline work")
    elif provider in ["huggingface", "hf"]:
        print("   ✅ Using HuggingFace provider")
        print("   ℹ️  Generates complete professional infographics")
        print("   ℹ️  Good for: Production, high-quality output")
    else:
        print(f"   ⚠️  Unknown provider: {provider}")
        print("   ℹ️  Valid values: mock, huggingface")
    
    # HuggingFace Configuration
    print(f"\n🤗 HuggingFace Model: {settings.hf_image_model}")
    
    if settings.hf_image_model == "Qwen/Qwen-Image-2512":
        print("   ✅ Using recommended model for complete infographics")
    else:
        print(f"   ℹ️  Using: {settings.hf_image_model}")
    
    print(f"\n🌐 HF Inference Provider: {settings.hf_inference_provider}")
    if settings.hf_inference_provider:
        print(f"   ✅ Using provider: {settings.hf_inference_provider}")
    else:
        print("   ℹ️  Using default HuggingFace endpoint")
    
    # Token
    print(f"\n🔑 HuggingFace Token: ", end="")
    if settings.hf_token:
        token_preview = settings.hf_token[:10] + "..." if len(settings.hf_token) > 10 else settings.hf_token
        print(f"✅ Set ({token_preview})")
        print("   ℹ️  Token is configured and will be used for API calls")
    else:
        print("❌ Not Set")
        if provider in ["huggingface", "hf"]:
            print("   ⚠️  WARNING: HuggingFace provider requires HF_TOKEN!")
            print("   ℹ️  Get token from: https://huggingface.co/settings/tokens")
            print("   ℹ️  Or switch to: IMAGE_PROVIDER=mock")
        else:
            print("   ℹ️  Not needed for mock provider")
    
    # Output Directory
    print(f"\n📁 Output Directory: {settings.image_output_dir}")
    output_path = Path(settings.image_output_dir)
    if output_path.exists():
        print(f"   ✅ Directory exists")
        images = list(output_path.glob("*.png"))
        print(f"   ℹ️  Contains {len(images)} PNG file(s)")
    else:
        print(f"   ℹ️  Will be created on first generation")
    
    # Overall Status
    print("\n" + "=" * 60)
    print("OVERALL STATUS")
    print("=" * 60)
    
    issues = []
    warnings = []
    
    if provider in ["huggingface", "hf"] and not settings.hf_token:
        issues.append("HF_TOKEN not set (required for HuggingFace provider)")
    
    if not settings.hf_image_model:
        warnings.append("HF_IMAGE_MODEL not set (will use default)")
    
    if issues:
        print("\n❌ ISSUES FOUND:")
        for issue in issues:
            print(f"   • {issue}")
        print("\n💡 Fix these issues before using IMAGE_PROVIDER=huggingface")
    elif warnings:
        print("\n⚠️  WARNINGS:")
        for warning in warnings:
            print(f"   • {warning}")
        print("\n✅ Configuration is valid but can be improved")
    else:
        print("\n✅ Configuration looks good!")
    
    # Recommendations
    print("\n" + "=" * 60)
    print("RECOMMENDATIONS")
    print("=" * 60)
    
    if provider in ["mock", "svg", "local_svg", "local"]:
        print("\n🧪 You're using Mock Provider:")
        print("   • Fast generation (1-2 seconds)")
        print("   • No API costs")
        print("   • Good for development/testing")
        print("\n💡 To use production-quality infographics:")
        print("   1. Get HF token: https://huggingface.co/settings/tokens")
        print("   2. Update .env: IMAGE_PROVIDER=huggingface")
        print("   3. Update .env: HF_TOKEN=hf_your_token_here")
        print("   4. Restart backend")
    else:
        print("\n🚀 You're using HuggingFace Provider:")
        print("   • Professional infographic quality")
        print("   • Includes text, characters, illustrations")
        print("   • First request: 5-10 seconds (cold start)")
        print("   • Subsequent: 3-5 seconds")
        print("\n💡 To test locally without API costs:")
        print("   1. Update .env: IMAGE_PROVIDER=mock")
        print("   2. Restart backend")
    
    print("\n" + "=" * 60)
    print("NEXT STEPS")
    print("=" * 60)
    print("\n1. Start backend:")
    print("   cd backend")
    print("   uvicorn app.main:app --reload --port 8000")
    print("\n2. Test Phase 4:")
    print("   pytest tests/test_images.py -v")
    print("\n3. Generate infographic:")
    print("   • Via API: POST http://localhost:8000/api/images/generate/{post_id}")
    print("   • Via Streamlit: http://localhost:8501")
    print("\n" + "=" * 60 + "\n")

if __name__ == "__main__":
    try:
        check_config()
    except Exception as e:
        print(f"\n❌ Error checking configuration: {e}")
        print("\nMake sure you're running this from the backend directory:")
        print("  cd backend")
        print("  python check_phase4_config.py")
        sys.exit(1)
