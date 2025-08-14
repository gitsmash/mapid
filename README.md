# Mapid

Location-based community platform for neighborhood connections.

## Development

This project uses uv for dependency management and Flask for the web framework.

### Setup

```bash
# Create virtual environment
uv venv

# Activate virtual environment  
source .venv/bin/activate

# Install dependencies
uv sync --dev
```

### Running

```bash
# Start the application
./mapid.sh start
```

### Testing

```bash
# Run tests
uv run pytest
```