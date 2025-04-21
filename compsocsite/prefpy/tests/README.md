# OPRA Allocation Mechanisms Test Suite

This directory contains tests for evaluating allocation mechanisms in the OPRA system. The tests measure correctness, performance, and fairness properties of different algorithms.

## File Structure

- `run_mechanism_tests.py` - Main entry point for running tests
- `test_allocation_mechanisms.py` - Implementation of allocation mechanism tests
- `test_mechanism.py` - Base test classes and utility functions
- `generate_test_instances.py` - Script to generate test data
- `test_instances/` - Directory containing test data files
- `allocation_tests_report.txt` - Generated report with detailed test results

## Running Tests

### Basic Usage

Run from the `compsocsite` directory:

```bash
# Navigate to the compsocsite directory
cd /opra/compsocsite

# Run as a Python module
python -m prefpy.tests.run_mechanism_tests
```

### Command Line Options

```bash
# Generate new Dirichlet instances before testing
python -m prefpy.tests.run_mechanism_tests --dirichlet

# Specify number of test instances (default is 100)
python -m prefpy.tests.run_mechanism_tests --dirichlet --instances 50
```

### Alternative Method (Django Environment)

If you need the Django environment for testing:

```bash
# From compsocsite directory
python manage.py shell

# In the shell
exec(open('prefpy/tests/run_mechanism_tests.py').read())
```

## Test Output

After running tests:

1. A summary will be printed to the console showing:
   - Success/failure counts
   - Performance statistics for each algorithm
   - Any property violations detected

2. Detailed results are saved in `allocation_tests_report.txt` including:
   - Input parameters for each test
   - Allocation results
   - Timing information
   - Property verification results

## Generating Test Instances

To create new test instances without running tests:

```bash
python -m prefpy.tests.generate_test_instances
```

This will generate Dirichlet instances with various parameters and save them to the `test_instances` directory.

## Troubleshooting

- If you see "in phase 2" repeatedly in the output, this is normal behavior from Python's unittest module during test discovery.
- If tests fail with import errors, ensure you're running from the correct directory (compsocsite root).
- Performance can vary significantly based on the allocation mechanism and instance size.