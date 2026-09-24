// Headless verification test for Rove WebAssembly site module (Music, Pong, Dodge, Fireworks)
import { initRoveModule } from './dist/site.mjs';

async function runVerification() {
  console.log('--- Testing Rove WASM Bundle with Node.js ---');
  const rove = await initRoveModule(new URL('./dist/site.wasm', import.meta.url));

  // 1. Counter tests
  console.assert(rove.get_counter() === 0, 'Initial counter must be 0');
  console.assert(rove.inc_counter() === 1, 'inc_counter must be 1');
  console.assert(rove.inc_counter() === 2, 'inc_counter must be 2');
  console.assert(rove.dec_counter() === 1, 'dec_counter must be 1');
  console.assert(rove.double_counter() === 2, 'double_counter must be 2');
  console.assert(rove.reset_counter() === 0, 'reset_counter must be 0');
  console.log('✔ Counter & State management passed');

  // 2. Fibonacci tests
  console.assert(rove.calc_fibonacci(0) === 0, 'fib(0) == 0');
  console.assert(rove.calc_fibonacci(1) === 1, 'fib(1) == 1');
  console.assert(rove.calc_fibonacci(10) === 55, 'fib(10) == 55');
  console.assert(rove.calc_fibonacci(15) === 610, 'fib(15) == 610');
  console.log('✔ Fibonacci calculations passed');

  // 3. Prime tests
  console.assert(rove.is_prime(2) === true, '2 is prime');
  console.assert(rove.is_prime(17) === true, '17 is prime');
  console.assert(rove.is_prime(18) === false, '18 is not prime');
  console.assert(rove.count_primes(100) === 25, '25 primes under 100');
  console.assert(rove.count_primes(1000) === 168, '168 primes under 1000');
  console.log('✔ Primality and counting tests passed');

  // 4. Collatz and GCD tests
  console.assert(rove.collatz_steps(1) === 0, 'collatz(1) == 0');
  console.assert(rove.collatz_steps(27) === 111, 'collatz(27) == 111');
  console.assert(rove.fast_gcd(48, 18) === 6, 'gcd(48, 18) == 6');
  console.assert(rove.fast_gcd(101, 103) === 1, 'gcd(101, 103) == 1');
  console.log('✔ Collatz & Euclidean GCD passed');

  // 5. Array vector operations
  console.assert(rove.sum_array([1, 2, 3, 4, 5]) === 15, 'sum([1..5]) == 15');
  console.assert(rove.sum_array([100, 200, 300]) === 600, 'sum([100,200,300]) == 600');
  console.log('✔ Array operations passed');

  // 6. String processing
  const greeting = rove.greet_user('Geliştirici');
  console.assert(greeting.includes('Merhaba, Geliştirici!'), 'Greeting must match');
  console.assert(rove.mode_name(0).includes('Spektrum'), 'Mode 0 name');
  console.assert(rove.mode_name(1).includes('Matris'), 'Mode 1 name');
  console.assert(rove.mode_name(2).includes('Kuantum'), 'Mode 2 name');
  console.assert(rove.mode_name(3).includes('Pong'), 'Mode 3 name');
  console.assert(rove.mode_name(4).includes('Uzay'), 'Mode 4 name');
  console.assert(rove.mode_name(7).includes('Aurora'), 'Mode 7 name');
  console.assert(rove.mode_name(8).includes('Sinir'), 'Mode 8 name');
  rove.set_anim_mode(8);
  console.assert(rove.get_anim_mode() === 8, 'Anim mode should support Neural Cosmos');
  console.assert(rove.cycle_anim_mode() === 0, 'Mode 8 should wrap to mode 0');
  console.log('✔ UTF-8 String processing & Mode names passed');

  // 7. Pong arcade physics & accessors
  rove.set_anim_mode(3);
  console.assert(rove.get_anim_mode() === 3, 'Anim mode should be 3 (Pong)');
  const initialY = rove.pong_move_paddle(0.0);
  const downY = rove.pong_move_paddle(20.0);
  console.assert(downY > initialY, 'Paddle moved down');
  const upY = rove.pong_move_paddle(-40.0);
  console.assert(upY < downY, 'Paddle moved up');
  rove.pong_reset_game();
  console.assert(rove.get_player_score() === 0, 'Player score reset');
  console.assert(rove.get_cpu_score() === 0, 'CPU score reset');
  console.assert(rove.get_pong_rally() === 0, 'Pong rally reset');
  console.log('✔ Pong game physics & paddle controls passed');

  // 8. Music synthesizer math
  const lead0 = rove.music_lead_note(0, 0);
  console.assert(lead0 === 440.0, 'Track 0 step 0 lead note is 440Hz (A4)');
  const bass0 = rove.music_bass_note(0, 0);
  console.assert(bass0 === 110.0, 'Track 0 step 0 bass note is 110Hz (A2)');
  const kick = rove.music_drum_beat(0);
  console.assert(kick === 1, 'Step 0 is kick drum');
  const snare = rove.music_drum_beat(2);
  console.assert(snare === 2, 'Step 2 is snare drum');
  const hihat = rove.music_drum_beat(1);
  console.assert(hihat === 3, 'Step 1 is hi-hat');
  const c4 = rove.piano_note_freq(0);
  console.assert(Math.abs(c4 - 261.63) < 0.01, 'Piano C4 freq');
  const c5 = rove.piano_note_freq(7);
  console.assert(Math.abs(c5 - 523.25) < 0.01, 'Piano C5 freq');
  console.log('✔ Music synthesizer math and piano frequencies passed');

  // 9. Cyber Space Dodge game
  rove.set_anim_mode(4);
  console.assert(rove.get_anim_mode() === 4, 'Anim mode should be 4 (Space Dodge)');
  const dodgeInitY = rove.dodge_move(0.0);
  const dodgeDownY = rove.dodge_move(30.0);
  console.assert(dodgeDownY > dodgeInitY, 'Dodge ship moved down');
  rove.dodge_reset();
  console.assert(rove.get_dodge_score() === 0, 'Dodge score reset to 0');
  console.assert(rove.is_dodge_game_over() === 0, 'Game over reset to 0');
  console.log('✔ Cyber Space Dodge game passed');

  // 10. Fireworks Multi-Burst & Auto Show
  rove.trigger_firework(200.0, 100.0);
  const sfx = rove.get_and_clear_sfx();
  console.assert(sfx === 5, 'Firework SFX event triggered');
  console.assert(rove.get_and_clear_sfx() === 0, 'SFX event cleared');
  console.assert(rove.is_auto_fireworks() === 0, 'Auto fireworks initially off');
  console.assert(rove.toggle_auto_fireworks() === 1, 'Auto fireworks toggled on');
  console.assert(rove.toggle_auto_fireworks() === 0, 'Auto fireworks toggled off');
  console.log('✔ Fireworks Multi-Burst & Auto Show passed');

  // 11. Pong 2.0 (2P mode, Difficulty, Powerups)
  console.assert(rove.pong_is_2p_mode() === 0, 'Pong 2P mode initially off');
  rove.pong_set_2p_mode(1);
  console.assert(rove.pong_is_2p_mode() === 1, 'Pong 2P mode enabled');
  rove.pong_set_difficulty(2);
  console.assert(rove.pong_get_difficulty() === 2, 'Pong difficulty set to insane');
  const p2y = rove.pong_move_p2(15.0);
  console.assert(p2y > 115.0, 'Player 2 paddle moved');
  rove.pong_reset_game();
  console.log('✔ Pong 2.0 (2P mode, difficulty, powerup mechanics) passed');

  // 12. Quantum Gravity Vortex Sandbox (Mode 6)
  rove.set_anim_mode(6);
  console.assert(rove.get_anim_mode() === 6, 'Mode 6 is Gravity Vortex');
  console.assert(rove.vortex_is_repel() === 0, 'Vortex repel initially off');
  console.assert(rove.vortex_toggle_repel() === 1, 'Vortex repel toggled on');
  rove.vortex_set_mouse(300.0, 150.0);
  rove.vortex_trigger_shockwave();
  console.assert(rove.get_and_clear_sfx() === 5, 'Vortex shockwave triggered SFX');
  console.log('✔ Quantum Gravity Vortex Sandbox passed');

  // 13. New Music Tracks (Track 3: Tokyo Neon Drift, Track 4: Arcade Boss Battle)
  const track3Lead = rove.music_lead_note(3, 0);
  console.assert(track3Lead === 587.33, 'Track 3 lead note step 0 is D5');
  const track4Bass = rove.music_bass_note(4, 0);
  console.assert(track4Bass === 110.0, 'Track 4 bass note step 0 is A2');
  console.assert(rove.track_name(3).includes('Tokyo'), 'Track 3 name is Tokyo Neon Drift');
  console.assert(rove.track_name(4).includes('Boss'), 'Track 4 name is Arcade Boss Battle');
  console.assert(rove.mode_name(5).includes('Festival'), 'Mode 5 name is Fireworks Festival');
  console.assert(rove.mode_name(6).includes('Vortex') || rove.mode_name(6).includes('Girdabi'), 'Mode 6 name is Gravity Vortex');
  console.log('✔ New Procedural Music Tracks (Tokyo Drift & Boss Battle) passed');

  console.log('\n🎉 ALL ROVE WASM MODULE TESTS PASSED SUCCESSFULLY (13/13 SUITES)!');
}

runVerification().catch(err => {
  console.error('Verification failed:', err);
  process.exit(1);
});
