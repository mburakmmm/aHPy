.. entry:: Require complete GitHub Action commit pins
   :type: build

   Corrected seven shortened ``actions/upload-artifact`` references that made
   the first hosted workflow fail before checkout. A quality regression now
   requires every external action in the aHPy workflow to use a full
   40-character commit SHA.
