Strong tests:
- focused production detector and alert-rule suites that clearly protect behavior
- real-media confidence tests when they cover detector behavior that synthetic inputs cannot prove

Weak or low-value tests:
- near-duplicate detector-lab threshold tests that differ only by tiny boundary variations
- tests that mostly prove the current internal helper wiring rather than meaningful behavior

Main risk:
- trimming too aggressively could remove useful calibration confidence, especially in detector-lab

Best cleanup:
- merge or parameterize the near-duplicate threshold cases
- keep the real-media confidence lane separate from the fast default lane
- fix environment-coupled tests by using committed fixtures, temp paths, or explicit skips

What not to cut:
- strong production behavior tests
- slow real-media confidence tests that cover genuinely unique signal
