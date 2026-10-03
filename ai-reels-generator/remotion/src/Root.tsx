import React from 'react';
import {CalculateMetadataFunction, Composition} from 'remotion';
import type {ReelProps} from './types';
import {Reel} from './Reel';
import {demoProps} from './demo';
import {Long} from './long/Long';
import {longDemoProps} from './long/demo';
import type {LongProps} from './long/types';
import {Stick} from './stick/Stick';
import {stickDemoProps} from './stick/demo';
import type {StickProps} from './stick/types';
import {Thumbnail, thumbSize, type ThumbProps} from './Thumbnail';
import {StickStory} from './story/Story';
import {storyDemoProps} from './story/demo';
import type {StoryProps} from './story/types';

// The length comes from the props (seconds), so each video is exactly as long
// as its voiceover. The Python pipeline passes real props with --props.
const calculateMetadata: CalculateMetadataFunction<ReelProps> = ({props}) => ({
  fps: props.fps,
  durationInFrames: Math.max(1, Math.ceil(props.duration * props.fps)),
});
const calculateStickMetadata: CalculateMetadataFunction<StickProps> = ({props}) => ({
  fps: props.fps,
  durationInFrames: Math.max(1, Math.ceil((props.scenes.reduce((t, s) => t + s.seconds, 0) + props.outroSeconds) * props.fps)),
});
const calculateLongMetadata: CalculateMetadataFunction<LongProps> = ({props}) => ({
  fps: props.fps,
  durationInFrames: Math.max(1, Math.ceil(props.duration * props.fps)),
});

const calculateStoryMetadata: CalculateMetadataFunction<StoryProps> = ({props}) => ({
  fps: props.fps,
  durationInFrames: Math.max(1, Math.ceil(props.duration * props.fps)),
  width: props.vertical ? 1080 : 1920,
  height: props.vertical ? 1920 : 1080,
});
const calculateThumbMetadata: CalculateMetadataFunction<ThumbProps> = ({props}) => thumbSize(props.wide);
const thumbDemo: ThumbProps = {src: 'thumb/frame.jpg', text: 'Why no tax cut', highlight: 'tax cut', side: 'left',
  focusX: 0.6, focusY: 0.5, zoom: 1.1, accent: '#ffd23f', accent2: '#ffd23f', wide: true};

export const RemotionRoot: React.FC = () => (
  <>
  <Composition
    id="Reel"
    component={Reel}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={300}
    defaultProps={demoProps}
    calculateMetadata={calculateMetadata}
  />
  {/* 16:9 long video (8-10 min), all motion graphics: reelgen/longform.py */}
  <Composition
    id="Long"
    component={Long}
    width={1920}
    height={1080}
    fps={30}
    durationInFrames={300}
    defaultProps={longDemoProps}
    calculateMetadata={calculateLongMetadata}
  />
  {/* 9:16 stick-figure comedy, all SVG line art */}
  <Composition
    id="Stick"
    component={Stick}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={300}
    defaultProps={stickDemoProps}
    calculateMetadata={calculateStickMetadata}
  />
  {/* 16:9 stick-figure comedy episode (3-8 min), a recurring cast: reelgen/stickstory.py */}
  <Composition
    id="StickStory"
    component={StickStory}
    width={1920}
    height={1080}
    fps={30}
    durationInFrames={300}
    defaultProps={storyDemoProps}
    calculateMetadata={calculateStoryMetadata}
  />
  {/* YouTube thumbnail from the video's own frame: reelgen/thumbnail.py (rendered as a still) */}
  <Composition
    id="Thumbnail"
    component={Thumbnail}
    width={1280}
    height={720}
    fps={30}
    durationInFrames={1}
    defaultProps={thumbDemo}
    calculateMetadata={calculateThumbMetadata}
  />
  </>
);
