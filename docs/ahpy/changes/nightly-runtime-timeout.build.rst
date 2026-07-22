Aligned both moving-nightly semantic builds with the validated ``-O0`` profile
and bounded them to 30 minutes so an optimization or dependency hang cannot
consume an unbounded runner and the unconditional evidence upload can still
record the result.
