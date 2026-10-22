#!/usr/bin/env python3
"""Check Agent Framework API."""

from agent_framework import Agent
import inspect

sig = inspect.signature(Agent.__init__)
print('Agent.__init__ parameters:')
for name, param in sig.parameters.items():
    if name != 'self':
        print(f'  {name}')
        
# Check the docstring
print('\nAgent docstring:')
print(Agent.__doc__ if Agent.__doc__ else '(no docstring)')
