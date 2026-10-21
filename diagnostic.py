#!/usr/bin/env python3
"""
Diagnostic tool to check environment and installation status.

Run this to verify:
- Python version
- Virtual environment status
- Dependencies installed
- Configuration files present
- Static files exist
- Network connectivity

Usage:
    python diagnostic.py
"""

import sys
import subprocess
from pathlib import Path


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def check_python_version():
    """Verify Python 3.11+."""
    print(f"\n{Colors.BOLD}Python Version{Colors.RESET}")
    major, minor, patch = sys.version_info[:3]
    version_str = f"{major}.{minor}.{patch}"
    
    if major >= 3 and minor >= 11:
        print(f"  {Colors.GREEN}✓{Colors.RESET} Python {version_str} (3.11+ required)")
        return True
    else:
        print(f"  {Colors.RED}✗{Colors.RESET} Python {version_str} (3.11+ required)")
        return False


def check_venv():
    """Check if virtual environment is active."""
    print(f"\n{Colors.BOLD}Virtual Environment{Colors.RESET}")
    
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        venv_path = sys.prefix
        print(f"  {Colors.GREEN}✓{Colors.RESET} Virtual environment active: {venv_path}")
        return True
    else:
        print(f"  {Colors.YELLOW}⚠{Colors.RESET} Virtual environment NOT active")
        print(f"     Activate with: .venv\\Scripts\\Activate.ps1 (Windows)")
        return False


def check_dependencies():
    """Check if required packages are installed."""
    print(f"\n{Colors.BOLD}Dependencies{Colors.RESET}")
    
    required_packages = {
        "fastapi": "FastAPI web framework",
        "uvicorn": "ASGI server",
        "python-dotenv": "Environment variable loading",
        "azure": "Azure SDK",
        "agent_framework": "Agent framework",
    }
    
    all_installed = True
    for package_name, description in required_packages.items():
        try:
            __import__(package_name)
            print(f"  {Colors.GREEN}✓{Colors.RESET} {package_name:<20} {description}")
        except ImportError:
            print(f"  {Colors.RED}✗{Colors.RESET} {package_name:<20} {description}")
            all_installed = False
    
    if not all_installed:
        print(f"\n  {Colors.YELLOW}To install:{Colors.RESET}")
        print("    pip install -r requirements.txt")
    
    return all_installed


def check_files():
    """Check that required files exist."""
    print(f"\n{Colors.BOLD}Project Files{Colors.RESET}")
    
    project_root = Path(__file__).parent
    required_files = {
        "main.py": "FastAPI application",
        "requirements.txt": "Python dependencies",
        ".vscode/launch.json": "VS Code debug config",
        "workflows/__init__.py": "Workflow module",
        "workflows/concurrent_workflow.py": "Concurrent workflow",
        "workflows/group_chat_workflow.py": "Group chat workflow",
        "workflows/sequential_workflow.py": "Sequential workflow",
        "workflows/approval_workflow.py": "Approval workflow",
        "workflows/game_workflow.py": "Game workflow",
        "static/index.html": "Dashboard UI",
        "static/css/style.css": "Dashboard styling",
        "static/js/dashboard.js": "Dashboard logic",
        "tests/conftest.py": "Pytest configuration",
        "tests/test_workflows_integration.py": "Integration tests",
    }
    
    all_present = True
    for file_path, description in required_files.items():
        full_path = project_root / file_path
        if full_path.exists():
            print(f"  {Colors.GREEN}✓{Colors.RESET} {file_path:<35} {description}")
        else:
            print(f"  {Colors.RED}✗{Colors.RESET} {file_path:<35} {description}")
            all_present = False
    
    return all_present


def check_configuration():
    """Check configuration files."""
    print(f"\n{Colors.BOLD}Configuration{Colors.RESET}")
    
    project_root = Path(__file__).parent
    env_file = project_root / ".env"
    
    # Check .env
    if env_file.exists():
        print(f"  {Colors.GREEN}✓{Colors.RESET} .env file exists")
        try:
            from dotenv import load_dotenv
            import os
            load_dotenv()
            
            required_vars = [
                "AZURE_OPENAI_API_KEY",
                "AZURE_OPENAI_ENDPOINT",
                "AZURE_OPENAI_DEPLOYMENT_NAME",
            ]
            
            missing = []
            for var in required_vars:
                if not os.getenv(var):
                    missing.append(var)
            
            if missing:
                print(f"  {Colors.YELLOW}⚠{Colors.RESET} Missing environment variables: {', '.join(missing)}")
                return False
            else:
                print(f"  {Colors.GREEN}✓{Colors.RESET} All required environment variables set")
                return True
        except Exception as e:
            print(f"  {Colors.RED}✗{Colors.RESET} Error loading .env: {e}")
            return False
    else:
        print(f"  {Colors.YELLOW}⚠{Colors.RESET} .env file not found")
        print(f"     Create one with Azure credentials for local testing")
        return False


def check_syntax():
    """Check Python syntax of key files."""
    print(f"\n{Colors.BOLD}Python Syntax{Colors.RESET}")
    
    import py_compile
    
    project_root = Path(__file__).parent
    files_to_check = [
        "main.py",
        "workflows/__init__.py",
        "workflows/concurrent_workflow.py",
        "workflows/group_chat_workflow.py",
        "workflows/sequential_workflow.py",
        "workflows/approval_workflow.py",
        "workflows/game_workflow.py",
    ]
    
    all_valid = True
    for file_path in files_to_check:
        full_path = project_root / file_path
        try:
            py_compile.compile(str(full_path), doraise=True)
            print(f"  {Colors.GREEN}✓{Colors.RESET} {file_path}")
        except py_compile.PyCompileError as e:
            print(f"  {Colors.RED}✗{Colors.RESET} {file_path}: {e}")
            all_valid = False
    
    return all_valid


def check_network():
    """Check if FastAPI is running (if app is started)."""
    print(f"\n{Colors.BOLD}Network Connectivity{Colors.RESET}")
    
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', 8000))
        sock.close()
        
        if result == 0:
            print(f"  {Colors.GREEN}✓{Colors.RESET} FastAPI running on http://localhost:8000")
            return True
        else:
            print(f"  {Colors.YELLOW}⚠{Colors.RESET} FastAPI not running on http://localhost:8000")
            print(f"     Start with: Press F5 in VS Code or 'uvicorn main:app --reload'")
            return False
    except Exception as e:
        print(f"  {Colors.RED}✗{Colors.RESET} Network check failed: {e}")
        return False


def main():
    """Run all diagnostic checks."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}HITL Dashboard Diagnostic Tool{Colors.RESET}\n")
    
    results = {
        "Python Version": check_python_version(),
        "Virtual Environment": check_venv(),
        "Dependencies": check_dependencies(),
        "Project Files": check_files(),
        "Configuration": check_configuration(),
        "Python Syntax": check_syntax(),
        "Network": check_network(),
    }
    
    # Summary
    print(f"\n{Colors.BOLD}Summary{Colors.RESET}")
    print("-" * 50)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for check, result in results.items():
        status = f"{Colors.GREEN}✓ PASS{Colors.RESET}" if result else f"{Colors.RED}✗ FAIL{Colors.RESET}"
        print(f"  {check:<25} {status}")
    
    print("-" * 50)
    print(f"  {Colors.BOLD}Total: {passed}/{total} checks passed{Colors.RESET}\n")
    
    # Recommendations
    if passed < total:
        print(f"{Colors.YELLOW}Recommendations:{Colors.RESET}")
        
        if not results["Virtual Environment"]:
            print("  1. Activate virtual environment: .venv\\Scripts\\Activate.ps1")
        
        if not results["Dependencies"]:
            print("  2. Install dependencies: pip install -r requirements.txt")
        
        if not results["Configuration"]:
            print("  3. Create .env file with Azure credentials")
        
        if not results["Python Syntax"]:
            print("  4. Review syntax errors above and fix them")
        
        if not results["Network"]:
            print("  5. Start FastAPI server: Press F5 or 'uvicorn main:app --reload'")
        
        print()
        return 1
    else:
        print(f"{Colors.GREEN}All checks passed! Ready to develop.{Colors.RESET}\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
