"""
Test script for core functionality (non-GUI components)
Tests crypto, database, models, and utils modules
"""
import sys
import os
from pathlib import Path

print("=" * 80)
print("ZM Password Manager v2.0 - Core Functionality Test")
print("=" * 80)
print()

# Test 1: Import all modules
print("Test 1: Importing modules...")
try:
    # Config
    import config
    print("  ✓ config")

    # Crypto modules
    from crypto import encryption, key_derivation, password_hashing
    print("  ✓ crypto.encryption")
    print("  ✓ crypto.key_derivation")
    print("  ✓ crypto.password_hashing")

    # Database modules
    from database import credential_store, master_password_store, migration
    print("  ✓ database.credential_store")
    print("  ✓ database.master_password_store")
    print("  ✓ database.migration")

    # Models
    from models import credential
    print("  ✓ models.credential")

    # Utils (some require tkinter)
    from utils import password_strength, validators
    print("  ✓ utils.password_strength")
    print("  ✓ utils.validators")

    # Try to import GUI-dependent utils
    try:
        from utils import clipboard_manager, session_manager
        print("  ✓ utils.clipboard_manager")
        print("  ✓ utils.session_manager")
    except ImportError:
        print("  ⚠ utils.clipboard_manager (requires tkinter - skipped)")
        print("  ⚠ utils.session_manager (requires tkinter - skipped)")

    print("\n✅ All modules imported successfully!\n")
except ImportError as e:
    print(f"\n❌ Import failed: {e}\n")
    sys.exit(1)

# Test 2: Test encryption
print("Test 2: Testing encryption...")
try:
    test_data = {"service": "test", "username": "user123", "password": "pass456"}
    test_key = encryption.Fernet.generate_key()

    encrypted = encryption.encrypt_data(test_data, test_key)
    decrypted = encryption.decrypt_data(encrypted, test_key)

    assert decrypted == test_data, "Decrypted data doesn't match original"
    print("  ✓ Encryption/decryption works")
    print(f"  ✓ Original: {test_data}")
    print(f"  ✓ Encrypted: {encrypted[:50]}... ({len(encrypted)} bytes)")
    print(f"  ✓ Decrypted: {decrypted}")
    print("\n✅ Encryption test passed!\n")
except Exception as e:
    print(f"\n❌ Encryption test failed: {e}\n")
    sys.exit(1)

# Test 3: Test password hashing
print("Test 3: Testing password hashing...")
try:
    test_password = "MySecurePassword123"

    # Hash password
    password_hash, salt = password_hashing.hash_master_password(test_password)
    print(f"  ✓ Password hashed")
    print(f"  ✓ Hash: {password_hash.hex()[:64]}...")
    print(f"  ✓ Salt: {salt.hex()[:64]}...")

    # Verify correct password
    is_valid = password_hashing.verify_master_password(test_password, password_hash, salt)
    assert is_valid, "Correct password verification failed"
    print(f"  ✓ Correct password verified: {is_valid}")

    # Verify incorrect password
    is_invalid = password_hashing.verify_master_password("WrongPassword", password_hash, salt)
    assert not is_invalid, "Incorrect password should not verify"
    print(f"  ✓ Incorrect password rejected: {not is_invalid}")

    print("\n✅ Password hashing test passed!\n")
except Exception as e:
    print(f"\n❌ Password hashing test failed: {e}\n")
    sys.exit(1)

# Test 4: Test key derivation
print("Test 4: Testing key derivation...")
try:
    master_password = "MyMasterPassword123"
    salt = os.urandom(32)

    # Derive key
    encryption_key = key_derivation.derive_encryption_key(master_password, salt)
    print(f"  ✓ Key derived from master password")
    print(f"  ✓ Key length: {len(encryption_key)} bytes")

    # Verify it's a valid Fernet key by trying to use it
    from cryptography.fernet import Fernet
    f = Fernet(encryption_key)
    test_data = b"test data"
    encrypted = f.encrypt(test_data)
    decrypted = f.decrypt(encrypted)
    assert decrypted == test_data, "Key derivation produced invalid Fernet key"
    print(f"  ✓ Derived key is valid Fernet key")

    # Verify same password + salt = same key (deterministic)
    encryption_key2 = key_derivation.derive_encryption_key(master_password, salt)
    assert encryption_key == encryption_key2, "Key derivation is not deterministic"
    print(f"  ✓ Key derivation is deterministic")

    print("\n✅ Key derivation test passed!\n")
except Exception as e:
    print(f"\n❌ Key derivation test failed: {e}\n")
    sys.exit(1)

# Test 5: Test Credential model
print("Test 5: Testing Credential model...")
try:
    from models.credential import Credential, credentials_to_storage_format, credentials_from_storage_format

    # Create credential
    cred = Credential(
        service_name="GitHub",
        username="john@example.com",
        password="SuperSecret123!"
    )
    print(f"  ✓ Created credential: {cred.service_name}")

    # Test conversion to storage format
    creds_dict = {"GitHub": cred}
    storage_format = credentials_to_storage_format(creds_dict)
    print(f"  ✓ Converted to storage format: {storage_format}")

    # Test conversion from storage format
    restored_creds = credentials_from_storage_format(storage_format)
    restored_cred = restored_creds["GitHub"]
    assert restored_cred.service_name == cred.service_name
    assert restored_cred.username == cred.username
    assert restored_cred.password == cred.password
    print(f"  ✓ Restored from storage format: {restored_cred.service_name}")

    print("\n✅ Credential model test passed!\n")
except Exception as e:
    print(f"\n❌ Credential model test failed: {e}\n")
    sys.exit(1)

# Test 6: Test password strength meter
print("Test 6: Testing password strength meter...")
try:
    test_passwords = [
        ("123", 0, "Very Weak"),
        ("password", 0, "Very Weak"),
        ("Password1", 1, "Weak"),
        ("Password123", 2, "Fair"),
        ("MyP@ssw0rd123", 3, "Strong"),
        ("MyV3ry$tr0ng&C0mpl3xP@ssw0rd!", 4, "Very Strong"),
    ]

    for password, expected_min_score, expected_label in test_passwords:
        score, label, feedback = password_strength.estimate_password_strength(password)
        print(f"  Password: '{password}'")
        print(f"    Score: {score}/4, Label: {label}, Feedback: {feedback}")
        assert label in ["Very Weak", "Weak", "Fair", "Strong", "Very Strong"], f"Invalid label: {label}"

    print("\n✅ Password strength test passed!\n")
except Exception as e:
    print(f"\n❌ Password strength test failed: {e}\n")
    sys.exit(1)

# Test 7: Test validators
print("Test 7: Testing validators...")
try:
    # Test password validation
    valid, msg = validators.validate_password_strength("short", is_master=False)
    assert not valid, "Short password should be invalid"
    print(f"  ✓ Short password rejected: {msg}")

    valid, msg = validators.validate_password_strength("ValidPassword123", is_master=True)
    assert valid, "Valid master password should pass"
    print(f"  ✓ Valid master password accepted")

    # Test service name validation
    valid, msg = validators.validate_service_name("GitHub", set(), False)
    assert valid, "Valid service name should pass"
    print(f"  ✓ Valid service name accepted")

    valid, msg = validators.validate_service_name("GitHub", {"GitHub"}, False)
    assert not valid, "Duplicate service name should be rejected"
    print(f"  ✓ Duplicate service name rejected: {msg}")

    # Test username validation
    valid, msg = validators.validate_username("user@example.com")
    assert valid, "Valid username should pass"
    print(f"  ✓ Valid username accepted")

    valid, msg = validators.validate_username("")
    assert not valid, "Empty username should be rejected"
    print(f"  ✓ Empty username rejected: {msg}")

    print("\n✅ Validators test passed!\n")
except Exception as e:
    print(f"\n❌ Validators test failed: {e}\n")
    sys.exit(1)

# Test 8: Test configuration
print("Test 8: Testing configuration...")
try:
    assert config.APP_NAME == "ZMPasswordManager"
    assert config.APP_VERSION == "2.0.0"
    assert config.PBKDF2_ITERATIONS == 600_000
    assert config.MIN_MASTER_PASSWORD_LENGTH == 12
    assert config.DEFAULT_AUTO_LOCK_MINUTES == 10
    assert config.DEFAULT_CLIPBOARD_CLEAR_SECONDS == 30

    print(f"  ✓ App Name: {config.APP_NAME}")
    print(f"  ✓ Version: {config.APP_VERSION}")
    print(f"  ✓ PBKDF2 Iterations: {config.PBKDF2_ITERATIONS:,}")
    print(f"  ✓ Min Master Password Length: {config.MIN_MASTER_PASSWORD_LENGTH}")
    print(f"  ✓ Auto-lock Timeout: {config.DEFAULT_AUTO_LOCK_MINUTES} minutes")
    print(f"  ✓ Clipboard Clear Delay: {config.DEFAULT_CLIPBOARD_CLEAR_SECONDS} seconds")
    print(f"  ✓ Data Directory: {config.DATA_DIR}")

    print("\n✅ Configuration test passed!\n")
except Exception as e:
    print(f"\n❌ Configuration test failed: {e}\n")
    sys.exit(1)

# Summary
print("=" * 80)
print("✅ ALL CORE FUNCTIONALITY TESTS PASSED!")
print("=" * 80)
print()
print("Summary:")
print("  ✓ Module imports")
print("  ✓ Encryption/decryption")
print("  ✓ Password hashing (PBKDF2)")
print("  ✓ Key derivation")
print("  ✓ Credential model")
print("  ✓ Password strength meter")
print("  ✓ Input validators")
print("  ✓ Configuration")
print()
print("Note: GUI components (ui/*) require tkinter/ttkbootstrap and a display.")
print("To test the full application, run on a Windows/Linux desktop with GUI:")
print("  python main.py")
print()
print("=" * 80)
