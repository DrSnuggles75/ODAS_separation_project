# Data structur breakdown.

## File types:
- .wav - either _sss-source-#.wav or _mix.wav
  - source-#.wav is one stream of the separated audio extracted from the /sss topic in odas.
  - mix.wav is the /sss topic fused into a single audio track to be used as a refrence.
- .txt - _angels.txt or clap.txt
  - _angles.txt hold information gathered from the /sst topic
   as well as calculated RMS values from each separated source.
   - From angels.txt the following is displayed.
    - Source id.
    - Azimuth angle +- drift of angle in degrees.
    - Elevation in degrees.
    - Rms value.
    - Number of audio frames captured.
    - Silent slots. Where the rms value is equal to 0.
    - Separation between the active sources. In degrees.
  - _clap.txt displays predictions of clap unfused model.
    - Can be MIX if --mix flag was used for that sample. (Mix will fuse the /sss audio into one source.)
    Otherwise it is the active sources that clap has done its zero-shot audio classification on.
    - fine refers to the cadidate labels provided via the general_fine.txt file.
    - Confidence score (softmax score -> 0.123) of CLAP prediction.
    - Fine cadidate label.
    - Which is then mapped to a set of corse cadidate labels. Fine -> Corse.
    - Last row displays the aggregated score of each corse mapping.
- .mp4 - Captures the vicon data and odas data in one visual media.
  - Can be used as ground truth to compare the placement of a sound source and the trigger of the /ssl or /sst topic.
- .png - Shows the cosine similraity between audio.
  - Used on CLAPs audio embeddings.
  - Lower score between sources is better.
