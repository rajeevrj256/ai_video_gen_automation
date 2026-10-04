import React from 'react';
import {Html5Audio, getInputProps} from 'remotion';

// Every sound in the editor goes through this. Long videos render the picture in one-minute parts with
// props `silent` (reelgen/video.py `_render_in_parts`) and the soundtrack once on its own. Even a --muted
// render still downloads every sound it meets, in the background, and a sound that started in a part's
// last frames was still downloading when the part finished and its file server closed: ECONNREFUSED,
// and the whole render failed (part 11 of a 1 h 39 min Script Video). Silent parts load no sound at all.
const isSilent = () => {
  try {
    return Boolean((getInputProps() as {silent?: boolean}).silent);
  } catch {
    return false;
  }
};

export const Audio: React.FC<React.ComponentProps<typeof Html5Audio>> = (props) => (isSilent() ? null : <Html5Audio {...props} />);
