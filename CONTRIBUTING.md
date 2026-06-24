# Contributing to SecureVault

First off, thank you for considering contributing to SecureVault! It's people like you that make SecureVault a great tool for everyone.

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the existing issues to avoid duplicates. When you create a bug report, include as many details as possible:

- **Use a clear and descriptive title**
- **Describe the exact steps to reproduce the problem**
- **Provide specific examples** to demonstrate the steps
- **Describe the behavior you observed** and what you expected
- **Include screenshots** if relevant
- **Note your environment**: OS version, Python version, etc.

### Suggesting Enhancements

Enhancement suggestions are welcome! Please provide:

- **A clear and descriptive title**
- **A detailed description of the proposed enhancement**
- **Explain why this would be useful** to most users
- **List any alternatives** you've considered

### Pull Requests

1. **Fork the repository** and create your branch from `main`
2. **Follow the existing code style**
   - Use meaningful variable names
   - Add comments for complex logic
   - Keep functions focused and small
3. **Add tests** if applicable
4. **Update documentation** if you change functionality
5. **Write a clear commit message**

## Development Setup

1. Clone your fork:
   ```bash
   git clone https://github.com/your-username/SecureVault.git
   cd SecureVault
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the application:
   ```bash
   python main.py
   ```

4. Run tests:
   ```bash
   python tests/test_core.py
   ```

## Code Style Guidelines

- **Follow PEP 8** for Python code style
- **Use descriptive names** for variables, functions, and classes
- **Write docstrings** for all public functions and classes
- **Keep functions under 50 lines** when possible
- **Add type hints** for function parameters and returns

## Security Considerations

⚠️ **This is a security-focused application**. When contributing:

- Never weaken existing security measures
- Always use cryptographically secure random generators
- Avoid logging sensitive information
- Be mindful of timing attacks
- Test security-related changes thoroughly

## Git Commit Messages

- Use the present tense ("Add feature" not "Added feature")
- Use the imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit the first line to 72 characters or less
- Reference issues and pull requests when relevant

Examples:
```
Add password export feature
Fix auto-lock timeout not resetting
Update README with new installation steps
```

## Testing

- Test your changes on Windows 10 and 11
- Ensure all existing tests pass
- Add new tests for new functionality
- Test edge cases (empty inputs, very long passwords, etc.)

## Documentation

- Update README.md if you change functionality
- Update BUILD_INSTRUCTIONS.md if you change the build process
- Add docstrings to new functions
- Update CLAUDE.md if architecture changes significantly

## Questions?

Feel free to open an issue labeled "question" if you need any clarification!

## Thank You!

Your contributions help make password management more secure and accessible for everyone. 🙏
