# Main goal

Let the local device run ffmpeg probe and mkvpropedit and ffmepg to get media data and keep that correct and then use ssh to tell remote machines to transcode the media if needed 


## Subgoals
  1. make sure that the checks run localy determine if the file needs to be transcoded at all to reduce network traffic
  2. maybe find a way better than smb to send the files
  3. let windows machines easily connect to the server so that I can enlist more help for the transcoding if needed
  1. write minimal code and get AI to write most of it from a very high level description of the problem
