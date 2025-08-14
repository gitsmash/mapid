"""Database CLI commands."""
import click
from flask import Blueprint
from flask.cli import with_appcontext
from app.extensions import db
from app.models.user import User
from app.models.category import PostCategory
from app.models.post import Post

bp = Blueprint("db_cli", __name__)


@bp.cli.command("init")
@with_appcontext
def init_db():
    """Initialize the database with tables and default data."""
    click.echo("Creating database tables...")
    db.create_all()
    
    click.echo("Creating default post categories...")
    categories = PostCategory.create_default_categories()
    click.echo(f"Created {len(categories)} post categories")
    
    click.echo("✅ Database initialization completed!")


@bp.cli.command("reset")
@click.confirmation_option(prompt="This will delete all data. Are you sure?")
@with_appcontext
def reset_db():
    """Reset the database (drop and recreate all tables)."""
    click.echo("Dropping all database tables...")
    db.drop_all()
    
    click.echo("Recreating database tables...")
    db.create_all()
    
    click.echo("Creating default post categories...")
    categories = PostCategory.create_default_categories()
    click.echo(f"Created {len(categories)} post categories")
    
    click.echo("✅ Database reset completed!")


@bp.cli.command("seed")
@with_appcontext
def seed_db():
    """Seed the database with sample data for development."""
    click.echo("Seeding database with sample data...")
    
    # This would be implemented later with sample data
    # For now, just ensure categories exist
    categories = PostCategory.create_default_categories()
    click.echo(f"Ensured {len(categories)} post categories exist")
    
    click.echo("✅ Database seeding completed!")


@bp.cli.command("cleanup")
@with_appcontext
def cleanup_expired_posts():
    """Clean up expired posts."""
    click.echo("Cleaning up expired posts...")
    
    count = Post.cleanup_expired_posts()
    click.echo(f"Marked {count} expired posts as inactive")
    
    click.echo("✅ Cleanup completed!")