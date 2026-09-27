import type {StickProps} from './types';

// "POV: You check your bank balance after ordering food" (the user's own script).
export const stickDemoProps: StickProps = {
  fps: 30,
  scenes: [
    {seconds: 3.2, pose: 'sit', face: 'hungry', screen: 'menu', amount: '', caption: "POV: You order food when you're hungry 😂", extras: ['thought-food', 'drool']},
    {seconds: 3.0, pose: 'lean', face: 'happy', screen: 'placed', amount: '', caption: '"I\'ll just order something small."', extras: []},
    {seconds: 3.2, pose: 'sit', face: 'mischief', screen: 'add', amount: '', caption: '"Okay... but I need this too."', extras: ['tap', 'plus-ones']},
    {seconds: 3.4, pose: 'upright', face: 'shock', screen: 'total', amount: '₹847', caption: 'Total: ₹847 💀', extras: ['shake', 'zoom', 'alarm']},
    {seconds: 3.4, pose: 'slump', face: 'terrified', screen: 'bank', amount: '', caption: '"Wait... how much money do I have?"', extras: ['sweat', 'wallet']},
    {seconds: 3.8, pose: 'lying', face: 'dead', screen: 'balance', amount: '₹93', caption: 'Bank balance: ₹93 💀', extras: ['soul', 'wallet']},
  ],
  outro: 'Never order food while hungry.',
  outroSeconds: 3.0,
  sfx: null,
};
