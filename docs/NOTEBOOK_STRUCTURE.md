# Notebook Structure

This file documents the intended structure of the main Google Colab notebook.

## Structure Rules
- Each main code cell should have a matching text cell directly above it
- Helper function cells must appear before any cell that calls them
- The execution cell must be the final code cell
- The final review text cell should be the last cell in the notebook

## Current Cell Order

1. Opening Text Cell — Changelog / Overview

2. Text Cell 1 — Library Imports & Environment Setup  
3. Code Cell 1 — Library Imports

4. Text Cell 1A — Interactive Configuration  
5. Code Cell 1A — Interactive Configuration

6. Text Cell 2 — Notebook Configuration  
7. Code Cell 2 — Configuration Constants

8. Text Cell 3 — Technical Indicators  
9. Code Cell 3 — Indicator Functions

10. Text Cell 3A — Understanding Option Greeks  
11. Code Cell 3A — Black-Scholes Greeks Calculator

12. Text Cell 3B — Multi-Timeframe Analysis  
13. Code Cell 3B — Multi-Timeframe Functions

14. Text Cell 3C — Market Regime Filter  
15. Code Cell 3C — Market Regime Functions

16. Text Cell 4 — Reversal Detection Framework  
17. Code Cell 4 — Reversal Detection Functions

18. Text Cell 5 — Position Sizing & Risk Management  
19. Code Cell 5 — Position Sizing Functions

20. Text Cell 6 — Options Chain Retrieval  
21. Code Cell 6 — Options Chain Helpers

22. Text Cell 6A — Trade Journal Export  
23. Code Cell 6A — Trade Journal Functions

24. Text Cell 6B — Visualization Functions  
25. Code Cell 6B — Visualization Functions

26. Text Cell 7 — Main Scanner Function  
27. Code Cell 7 — Main Scanner Function

28. Code Cell 7A — Verification Check (optional utility cell)

29. Text Cell 8 — Backtesting Module  
30. Code Cell 8 — Backtesting Framework

31. Text Cell 8A — Backtest Diagnostics  
32. Code Cell 8A — Backtest Diagnostics

33. Text Cell 9 — Run Scanner  
34. Code Cell 9 — Execute Scanner / Backtest

35. Final Review Text Cell — Version Review

## Notes
- Older notebook versions are stored in `notebooks/archive/`
- The current working notebook is stored in `notebooks/`
- Future updates should modify only the cells that actually change
