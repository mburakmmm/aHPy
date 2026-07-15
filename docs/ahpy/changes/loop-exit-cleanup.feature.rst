Universal HPy bootstrap now supports return and raise inside continuing
``while`` and sequence-index ``for`` loops, plus mixed terminating and
continuing ``if`` branches. ``break`` and ``continue`` close body-iteration
owned handles and builders against the loop-entry lifetime snapshot before
transferring control. Coverage includes focused compiler tests, generated
module normal/Debug oracles, and an updated rejected fuzz corpus for the
remaining HPy 0.9 gaps.
