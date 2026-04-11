# PR-C: Notebooks and Dashboards

**Note to Reviewers: This pull request is the final progressive step incorporating the visualization and strictly stateless evaluation environments. The underlying quantitative curve solvers and risk engines belong entirely to PR-B. This PR strips away the infrastructure to focus solely on notebooks and reactive dashboard UIs.**

## 1. Notebooks Sandbox Environment
The `notebooks/` directory now serves as a robust sandbox for testing the mathematical correctness of our pricing pipelines. 
* By utilizing **simple stateless libraries**, the user controls all explicit inputs and outputs manually without any interference from the `reaktiv` event loop or DataHub.
* Using notebooks for purely stateless mathematical evaluation guarantees that the core quantitative functions are physically sound and that all DataHub `@ticking` and `store` dependencies are rigorously optional. 

## 2. Interactive Analytical Dashboards
The `dashboard/` directory demonstrates exactly how to interface the complex reactive structures from PR-B (Swaps, Curves, Schedules) into streamlined interactive layouts.
