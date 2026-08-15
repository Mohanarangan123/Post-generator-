"""
Manual test script for image generation endpoint.

This script:
1. Checks database for existing posts
2. Creates a test post if none exist
3. Calls the image generation API
4. Verifies the generated image file
"""
import sys
import asyncio
from pathlib import Path
from uuid import uuid4

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.models.content_plan import ContentPlanModel, DayTopicModel
from app.models.post import PostModel, PostStatus
from app.services.image_service import run_pipeline


def check_database():
    """Check what data exists in the database."""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    
    with engine.connect() as conn:
        plans_count = conn.execute(text("SELECT COUNT(*) FROM content_plans")).scalar()
        posts_count = conn.execute(text("SELECT COUNT(*) FROM posts")).scalar()
        images_count = conn.execute(text("SELECT COUNT(*) FROM images")).scalar()
        
        print(f"📊 Database Status:")
        print(f"  Content Plans: {plans_count}")
        print(f"  Posts: {posts_count}")
        print(f"  Images: {images_count}")
        
        if posts_count > 0:
            result = conn.execute(text("""
                SELECT p.id, dt.day_number, dt.title, p.status
                FROM posts p
                JOIN day_topics dt ON p.day_topic_id = dt.id
                LIMIT 5
            """))
            print(f"\n  Sample Posts:")
            for row in result:
                print(f"    - Day {row[1]}: {row[2]} (status: {row[3]})")
        
        return plans_count, posts_count


def create_test_data(Session):
    """Create a test content plan with one post."""
    print("\n📝 Creating test data...")
    
    session = Session()
    try:
        # Create a content plan
        plan = ContentPlanModel(
            id=uuid4(),
            main_subject="Python Testing",
            number_of_days=1,
            audience="developers",
            difficulty="Beginner",
        )
        session.add(plan)
        session.flush()
        print(f"  ✓ Created content plan: {plan.main_subject}")
        
        # Create a day topic
        topic = DayTopicModel(
            id=uuid4(),
            plan_id=plan.id,
            day_number=1,
            main_subject="Python Testing",
            title="Introduction to Unit Testing",
            short_description="Learn the basics of unit testing in Python.",
            difficulty="Beginner",
            category="Testing",
            learning_objective="Understand unit testing fundamentals and write your first test.",
        )
        session.add(topic)
        session.flush()
        print(f"  ✓ Created day topic: {topic.title}")
        
        # Create a post
        post = PostModel(
            id=uuid4(),
            day_topic_id=topic.id,
            content="""DAY 01: Introduction to Unit Testing

Unit testing is a fundamental practice in software development that helps ensure your code works as expected.

Key Benefits:
• Catch bugs early in development
• Make refactoring safer
• Document code behavior through tests
• Improve code quality and maintainability

Getting Started:
Python includes the built-in 'unittest' module, making it easy to start writing tests. You can also use popular third-party libraries like pytest for more features.

Example:
```python
def test_addition():
    assert 1 + 1 == 2
```

Best Practices:
- Write tests before or alongside your code
- Keep tests simple and focused
- Test edge cases and error conditions
- Run tests frequently during development

#LearnWithAI #PythonTesting #SoftwareEngineering""",
            status=PostStatus.DRAFT,
            version=1,
        )
        session.add(post)
        session.commit()
        print(f"  ✓ Created post: {post.id}")
        
        return post.id
        
    except Exception as e:
        session.rollback()
        print(f"  ✗ Error creating test data: {e}")
        raise
    finally:
        session.close()


def get_existing_post(Session):
    """Get an existing post from the database."""
    session = Session()
    try:
        post = session.query(PostModel).filter(
            PostModel.status == PostStatus.DRAFT
        ).first()
        
        if post:
            print(f"\n📄 Using existing post: {post.id}")
            return post.id
        return None
    finally:
        session.close()


async def test_image_generation(post_id):
    """Test the image generation pipeline."""
    print(f"\n🎨 Testing image generation for post {post_id}...")
    
    settings = get_settings()
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Run the pipeline
        print("  → Running pipeline...")
        image = await run_pipeline(post_id, session)
        
        print(f"\n📊 Image Generation Result:")
        print(f"  ID: {image.id}")
        print(f"  Status: {image.status}")
        print(f"  Provider: {image.provider}")
        print(f"  File Path: {image.file_path}")
        print(f"  Dimensions: {image.width}x{image.height}")
        
        if image.status == "COMPLETED":
            print(f"\n✅ SUCCESS! Image generated successfully.")
            
            # Verify file exists
            if image.file_path:
                file_path = Path(image.file_path)
                if file_path.exists():
                    file_size = file_path.stat().st_size
                    print(f"  ✓ File exists: {file_path}")
                    print(f"  ✓ File size: {file_size:,} bytes")
                    
                    # Try to open with PIL to verify it's a valid image
                    try:
                        from PIL import Image as PILImage
                        img = PILImage.open(file_path)
                        print(f"  ✓ Valid image format: {img.format}")
                        print(f"  ✓ Image size: {img.size}")
                        img.close()
                    except Exception as e:
                        print(f"  ✗ Error opening image: {e}")
                else:
                    print(f"  ✗ File not found: {file_path}")
            
            # Print visual spec summary
            if image.visual_spec:
                print(f"\n📋 Visual Spec:")
                print(f"  Title: {image.visual_spec.get('title')}")
                print(f"  Day: {image.visual_spec.get('day_number')}")
                print(f"  Style: {image.visual_spec.get('style')}")
                print(f"  Aspect Ratio: {image.visual_spec.get('aspect_ratio')}")
                print(f"  Key Points: {len(image.visual_spec.get('key_points', []))}")
            
            return True
        else:
            print(f"\n❌ FAILED: Image status is {image.status}")
            return False
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()


def main():
    """Main test execution."""
    print("=" * 70)
    print("Image Generation Manual Test")
    print("=" * 70)
    
    settings = get_settings()
    print(f"\n⚙️  Configuration:")
    print(f"  Database: {settings.database_url.split('@')[-1]}")
    print(f"  Ollama: {settings.ollama_base_url}")
    print(f"  Model: {settings.ollama_model}")
    print(f"  Image Provider: {settings.image_provider}")
    print(f"  Output Dir: {settings.image_output_dir}")
    
    # Check database
    plans_count, posts_count = check_database()
    
    # Get or create test post
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    
    if posts_count > 0:
        post_id = get_existing_post(Session)
        if not post_id:
            post_id = create_test_data(Session)
    else:
        post_id = create_test_data(Session)
    
    # Test image generation
    success = asyncio.run(test_image_generation(post_id))
    
    print("\n" + "=" * 70)
    if success:
        print("✅ TEST PASSED: Image generation working correctly!")
    else:
        print("❌ TEST FAILED: Check errors above")
    print("=" * 70)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
