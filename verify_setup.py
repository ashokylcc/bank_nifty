#!/usr/bin/env python
"""
Quick verification script to check if all components are in place
"""
import os
import sys

def check_file_exists(filepath):
    """Check if file exists"""
    if os.path.exists(filepath):
        print(f"✅ {filepath}")
        return True
    else:
        print(f"❌ {filepath} - MISSING")
        return False

def main():
    """Verify setup"""
    print("🔍 Verifying BankNifty Momentum Breakout Strategy Setup\n")
    
    files_to_check = [
        # Core Django files
        "trading/__init__.py",
        "trading/apps.py",
        "trading/models.py",
        "trading/admin.py",
        "trading/views.py",
        
        # Services
        "trading/services/__init__.py",
        "trading/services/data_ingest.py",
        "trading/services/range_detector.py",
        "trading/services/momentum.py",
        "trading/services/strike_selector.py",
        "trading/services/risk_manager.py",
        "trading/services/execution_adapter.py",
        "trading/services/strategy_engine.py",
        
        # Utils
        "trading/utils/__init__.py",
        "trading/utils/time_helpers.py",
        "trading/utils/expiry_functions.py",
        "trading/utils/holidays.py",
        
        # Management
        "trading/management/__init__.py",
        "trading/management/commands/__init__.py",
        "trading/management/commands/run_strategy.py",
        
        # Tests
        "trading/tests/__init__.py",
        "trading/tests/test_expiry_functions.py",
        "trading/tests/test_momentum.py",
        "trading/tests/test_risk_manager.py",
        "trading/tests/test_execution_adapter.py",
        "trading/tests/test_integration.py",
        
        # Config
        "Dockerfile",
        "docker-compose.yml",
        "requirements.txt",
        
        # Documentation
        "README.md",
        "RUNBOOK.md",
        "GENERATION_SUMMARY.md",
        
        # Sample data
        "sample_data.csv",
    ]
    
    all_present = True
    for filepath in files_to_check:
        if not check_file_exists(filepath):
            all_present = False
    
    print("\n" + "="*60)
    if all_present:
        print("✅ All files present! Setup looks good.")
        print("\nNext steps:")
        print("1. Run migrations: python manage.py migrate")
        print("2. Create superuser: python manage.py createsuperuser")
        print("3. Create strategy in Django Admin")
        print("4. Run in dry-run: python manage.py run_strategy --dry-run")
    else:
        print("❌ Some files are missing. Please check above.")
        sys.exit(1)

if __name__ == "__main__":
    main()

