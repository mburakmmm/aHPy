.. entry:: Keyless release attestations
   :type: build

   Added a tag-only GitHub OIDC/Sigstore release gate that rebuilds clean,
   byte-reproducible evidence before creating SLSA provenance and SPDX SBOM
   attestations. Online and offline verification pins the repository, signer
   workflow, release tag, predicate, artifact digest, and hosted-runner policy.
