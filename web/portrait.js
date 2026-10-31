// LivingPortrait draws an old photo returning, on a WebGL canvas:
//   the photo as it is today -> a candle-light sweep mends it -> colour blooms out from
//   the face -> it settles into gentle depth that follows the pointer, under candlelight.
// The face is never moved or re-posed; only light, colour and depth change.

(function () {
  const VERT = `
    attribute vec2 aPos;
    varying vec2 vUv;
    void main() { vUv = aPos * 0.5 + 0.5; gl_Position = vec4(aPos, 0.0, 1.0); }`;

  const FRAG = `
    precision highp float;
    varying vec2 vUv;
    uniform sampler2D uBefore, uFinal, uDepth;
    uniform vec2 uOffset, uFace;
    uniform float uMend, uBloom, uSettled, uAspect, uTime;

    float luma(vec3 c) { return dot(c, vec3(0.299, 0.587, 0.114)); }

    void main() {
      vec2 uv = (vUv - 0.5) * 0.95 + 0.5;          // slight zoom so parallax never shows an edge
      float d0 = texture2D(uDepth, uv).r;
      uv += uOffset * (d0 - 0.45) * uSettled;      // nearer things move more
      float d = texture2D(uDepth, uv).r;

      vec3 before = texture2D(uBefore, uv).rgb;
      vec3 after = texture2D(uFinal, uv).rgb;
      vec3 gray = vec3(luma(after));

      float fromTop = 1.0 - uv.y;
      float mended = 1.0 - smoothstep(uMend - 0.07, uMend, fromTop);
      float sweep = exp(-pow((fromTop - uMend) / 0.014, 2.0)) * step(0.001, uMend) * step(uMend, 0.999);

      vec2 q = (uv - uFace) * vec2(uAspect, 1.0);
      float reach = uBloom * 1.7;
      float coloured = 1.0 - smoothstep(reach - 0.2, reach, length(q));

      vec3 col = mix(before, gray, mended);
      col = mix(col, after, coloured * mended);

      float flick = 0.95 + 0.03 * sin(uTime * 7.1) + 0.02 * sin(uTime * 13.7 + 1.3) + 0.015 * sin(uTime * 3.3 + 0.4);
      float light = mix(1.0, (0.84 + 0.24 * d) * flick, uSettled);
      col *= mix(vec3(1.0), vec3(1.0, 0.87, 0.68), 0.15 * uSettled) * light;
      col += vec3(1.0, 0.76, 0.42) * sweep * 0.5;

      vec2 v = vUv - 0.5;
      col *= 1.0 - dot(v, v) * 0.6;
      gl_FragColor = vec4(col, 1.0);
    }`;

  const ease = (t) => (t <= 0 ? 0 : t >= 1 ? 1 : 1 - Math.pow(1 - t, 3));
  const span = (t, a, b) => ease((t - a) / (b - a));

  function loadImage(src) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error(`Could not load ${src}`));
      img.src = src;
    });
  }

  class LivingPortrait {
    constructor(canvas) {
      this.canvas = canvas;
      this.reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
      const gl = canvas.getContext("webgl", { antialias: false, alpha: false });
      if (!gl) throw new Error("WebGL is not available");
      this.gl = gl;
      this.program = this.#program(VERT, FRAG);
      gl.useProgram(this.program);
      const buf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
      const loc = gl.getAttribLocation(this.program, "aPos");
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
      this.u = {};
      for (const n of ["uBefore", "uFinal", "uDepth", "uOffset", "uFace", "uMend", "uBloom", "uSettled", "uAspect", "uTime"]) {
        this.u[n] = gl.getUniformLocation(this.program, n);
      }
      this.textures = [gl.createTexture(), gl.createTexture(), gl.createTexture()];
      this.offset = [0, 0];
      this.target = [0, 0];
      this.lastPointer = -1e9;
      this.start = performance.now();
      this.ready = false;
      this.visible = true;

      const host = canvas.parentElement;
      host.addEventListener("pointermove", (e) => {
        const r = canvas.getBoundingClientRect();
        this.target = [((e.clientX - r.left) / r.width - 0.5) * 0.07, -((e.clientY - r.top) / r.height - 0.5) * 0.05];
        this.lastPointer = performance.now();
      });
      host.addEventListener("pointerleave", () => { this.lastPointer = -1e9; });
      window.addEventListener("deviceorientation", (e) => {
        if (e.gamma == null) return;
        this.target = [Math.max(-1, Math.min(1, e.gamma / 25)) * 0.035, Math.max(-1, Math.min(1, (e.beta - 45) / 25)) * 0.025];
        this.lastPointer = performance.now();
      });
      new ResizeObserver(() => this.#resize()).observe(canvas);
      new IntersectionObserver(([entry]) => { this.visible = entry.isIntersecting; }).observe(canvas);
      requestAnimationFrame((t) => this.#frame(t));
    }

    async show({ before, final, depth, face }) {
      const [a, b, c] = await Promise.all([loadImage(before), loadImage(final), loadImage(depth)]);
      const gl = this.gl;
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
      [a, b, c].forEach((img, i) => {
        gl.activeTexture(gl.TEXTURE0 + i);
        gl.bindTexture(gl.TEXTURE_2D, this.textures[i]);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, img);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      });
      gl.uniform1i(this.u.uBefore, 0);
      gl.uniform1i(this.u.uFinal, 1);
      gl.uniform1i(this.u.uDepth, 2);
      this.aspect = b.naturalWidth / b.naturalHeight;
      this.canvas.style.aspectRatio = `${b.naturalWidth} / ${b.naturalHeight}`;
      gl.uniform1f(this.u.uAspect, this.aspect);
      const f = face || { x: 0.5, y: 0.35 };
      gl.uniform2f(this.u.uFace, f.x, 1 - f.y);
      this.#resize();
      this.ready = true;
      this.play();
    }

    play() { this.start = performance.now(); }

    // Records one full return as a video the family can keep or share.
    async record(seconds = 9) {
      const types = ["video/mp4;codecs=avc1", "video/mp4", "video/webm;codecs=vp9", "video/webm"];
      const mimeType = types.find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported(t));
      if (!mimeType) throw new Error("This browser cannot record video.");
      const recorder = new MediaRecorder(this.canvas.captureStream(30), { mimeType, videoBitsPerSecond: 6e6 });
      const chunks = [];
      recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      const done = new Promise((resolve) => { recorder.onstop = resolve; });
      this.recording = true;
      this.play();
      recorder.start();
      await new Promise((r) => setTimeout(r, seconds * 1000));
      recorder.stop();
      await done;
      this.recording = false;
      return new Blob(chunks, { type: mimeType.split(";")[0] });
    }

    #resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = Math.round(this.canvas.clientWidth * dpr);
      const h = Math.round(this.canvas.clientHeight * dpr);
      if (w && h && (this.canvas.width !== w || this.canvas.height !== h)) {
        this.canvas.width = w;
        this.canvas.height = h;
      }
      this.gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    }

    #frame(now) {
      requestAnimationFrame((t) => this.#frame(t));
      if (!this.ready || (!this.visible && !this.recording)) return;
      const gl = this.gl;
      const t = this.reduced ? 99 : (now - this.start) / 1000;
      const mend = span(t, 0.9, 3.1);
      const bloom = span(t, 3.2, 5.8);
      const settled = span(t, 5.0, 6.8);

      const idle = now - this.lastPointer > 2500;
      const goal = this.reduced ? [0, 0]
        : idle ? [Math.sin(now / 2900) * 0.022, Math.cos(now / 3700) * 0.012] : this.target;
      this.offset[0] += (goal[0] - this.offset[0]) * 0.05;
      this.offset[1] += (goal[1] - this.offset[1]) * 0.05;

      gl.uniform1f(this.u.uMend, mend >= 1 ? 1.2 : mend);
      gl.uniform1f(this.u.uBloom, bloom);
      gl.uniform1f(this.u.uSettled, settled);
      gl.uniform2f(this.u.uOffset, this.offset[0], this.offset[1]);
      gl.uniform1f(this.u.uTime, this.reduced ? 0 : now / 1000);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }

    #program(vs, fs) {
      const gl = this.gl;
      const make = (type, src) => {
        const s = gl.createShader(type);
        gl.shaderSource(s, src);
        gl.compileShader(s);
        if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
        return s;
      };
      const p = gl.createProgram();
      gl.attachShader(p, make(gl.VERTEX_SHADER, vs));
      gl.attachShader(p, make(gl.FRAGMENT_SHADER, fs));
      gl.linkProgram(p);
      if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
      return p;
    }
  }

  window.LivingPortrait = LivingPortrait;
})();
