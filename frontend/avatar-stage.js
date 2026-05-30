/**
 * Prosecuto — 3D avatar stage (Three.js + GLB)
 * Neck-up portrait framing, facing the viewer.
 */
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const DEFAULT_MODEL = 'assets/avatar-khoshtip.glb';
const DEG = Math.PI / 180;

function pickClip(clips, keywords) {
  if (!clips?.length) return null;
  const lower = keywords.map((k) => k.toLowerCase());
  return (
    clips.find((c) => lower.some((k) => c.name.toLowerCase().includes(k))) ||
    clips[0]
  );
}

function enhanceMaterials(root, renderer) {
  const aniso = renderer.capabilities.getMaxAnisotropy();
  root.traverse((child) => {
    if (!child.isMesh) return;
    child.frustumCulled = false;
    const mats = Array.isArray(child.material) ? child.material : [child.material];
    mats.forEach((m) => {
      if (m.map) {
        m.map.anisotropy = aniso;
        m.map.generateMipmaps = true;
        m.map.minFilter = THREE.LinearMipmapLinearFilter;
        m.map.magFilter = THREE.LinearFilter;
      }
      if (m.normalMap) m.normalMap.anisotropy = aniso;
      if ('roughness' in m) m.roughness = Math.min(m.roughness ?? 1, 0.72);
      if ('metalness' in m) m.metalness = Math.min(m.metalness ?? 0, 0.15);
      m.needsUpdate = true;
    });
  });
}

class AvatarStage {
  constructor(container, options = {}) {
    this.container = container;
    this.modelUrl = options.modelUrl || DEFAULT_MODEL;
    this.speaking = false;
    this.disposed = false;
    this.pivot = null;
    this.rig = null;
    this.headBone = null;
    this.neckBone = null;
    this.leftEye = null;
    this.rightEye = null;
    this.lookTarget = new THREE.Vector3();
    this._tmp = new THREE.Vector3();
    this._quat = new THREE.Quaternion();

    this.scene = new THREE.Scene();
    this.clock = new THREE.Clock();
    this.mixer = null;
    this.idleAction = null;
    this.speakAction = null;

    const { width, height } = this._size();
    this.camera = new THREE.PerspectiveCamera(24, width / height, 0.02, 40);

    this.renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: 'high-performance',
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2.5));
    this.renderer.setSize(width, height);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.08;
    this.renderer.domElement.className = 'avatar-3d-canvas';
    container.appendChild(this.renderer.domElement);

    const key = new THREE.DirectionalLight(0xffffff, 1.55);
    key.position.set(0.6, 1.4, 2.2);
    this.scene.add(key);

    const fill = new THREE.DirectionalLight(0xd4e8f7, 0.75);
    fill.position.set(-1.8, 0.8, 1.4);
    this.scene.add(fill);

    const rim = new THREE.DirectionalLight(0xfff3d6, 0.45);
    rim.position.set(0.2, 1.1, -1.6);
    this.scene.add(rim);

    this.scene.add(new THREE.AmbientLight(0xf0f8ff, 0.42));
    this.scene.add(new THREE.HemisphereLight(0xeaf4fc, 0x5c6f85, 0.35));

    this._onResize = () => this._resize();
    this._ro = new ResizeObserver(this._onResize);
    this._ro.observe(container);

    this._load();
    this._tick = this._tick.bind(this);
    this._raf = requestAnimationFrame(this._tick);
  }

  _size() {
    const w = this.container.clientWidth || 400;
    const h = this.container.clientHeight || 500;
    return { width: w, height: h };
  }

  _resize() {
    const { width, height } = this._size();
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2.5));
    if (this.rig) this._framePortrait();
  }

  _findBones(root) {
    root.traverse((child) => {
      if (!child.isBone) return;
      if (child.name === 'Head') this.headBone = child;
      if (child.name === 'Neck') this.neckBone = child;
      if (child.name === 'LeftEye') this.leftEye = child;
      if (child.name === 'RightEye') this.rightEye = child;
    });
  }

  /** How much the face points toward the camera on +Z. */
  _faceTowardCameraScore() {
    const toCamera = new THREE.Vector3(0, 0, 1);

    if (this.leftEye && this.rightEye && this.headBone) {
      const le = new THREE.Vector3();
      const re = new THREE.Vector3();
      const head = new THREE.Vector3();
      this.leftEye.getWorldPosition(le);
      this.rightEye.getWorldPosition(re);
      this.headBone.getWorldPosition(head);
      const eyeMid = le.add(re).multiplyScalar(0.5);
      const faceForward = eyeMid.sub(head).normalize();
      return faceForward.dot(toCamera);
    }

    if (this.headBone) {
      const forward = new THREE.Vector3(0, 0, -1);
      forward.applyQuaternion(this.headBone.getWorldQuaternion(this._quat));
      return forward.dot(toCamera);
    }

    return 0;
  }

  _orientTowardCamera() {
    const candidates = [0, Math.PI, Math.PI / 2, -Math.PI / 2];
    let bestRot = 0;
    let bestScore = -Infinity;

    for (const rot of candidates) {
      this.pivot.rotation.y = rot;
      this.rig.updateMatrixWorld(true);
      const score = this._faceTowardCameraScore();
      if (score > bestScore) {
        bestScore = score;
        bestRot = rot;
      }
    }

    this.pivot.rotation.y = bestRot;
    this.rig.updateMatrixWorld(true);
  }

  _framePortrait() {
    if (!this.rig) return;

    this.rig.updateMatrixWorld(true);

    const full = new THREE.Box3().setFromObject(this.rig);
    const bodyH = full.max.y - full.min.y;

    let neckY = full.min.y + bodyH * 0.78;
    let headY = full.min.y + bodyH * 0.92;
    let topY = full.max.y;

    if (this.headBone && this.neckBone) {
      this.neckBone.getWorldPosition(this._tmp);
      neckY = this._tmp.y;
      this.headBone.getWorldPosition(this._tmp);
      headY = this._tmp.y;
      topY = Math.max(topY, headY + bodyH * 0.06);
    }

    const portraitBottom = neckY - bodyH * 0.03;
    const portraitTop = topY + bodyH * 0.015;
    const portraitMid = (portraitBottom + portraitTop) * 0.5;
    const portraitH = portraitTop - portraitBottom;

    this.lookTarget.set(0, headY - bodyH * 0.02, 0);

    const vFov = this.camera.fov * DEG;
    const fill = 0.94;
    const dist = (portraitH * 0.5) / (Math.tan(vFov * 0.5) * fill);

    this.camera.position.set(0, portraitMid + portraitH * 0.04, dist);
    this.camera.lookAt(this.lookTarget);
    this.camera.updateProjectionMatrix();
  }

  _setupPortrait(object) {
    enhanceMaterials(object, this.renderer);
    this._findBones(object);

    this.pivot = new THREE.Group();
    this.rig = object;
    this.pivot.add(object);
    this.scene.add(this.pivot);

    const box = new THREE.Box3().setFromObject(object);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());

    object.position.x -= center.x;
    object.position.z -= center.z;
    object.position.y -= box.min.y;

    const targetBodyH = 1.72;
    const scale = targetBodyH / size.y;
    object.scale.setScalar(scale);

    this._orientTowardCamera();
    this._framePortrait();
  }

  _load() {
    const loader = new GLTFLoader();
    loader.load(
      this.modelUrl,
      (gltf) => {
        if (this.disposed) return;
        this._setupPortrait(gltf.scene);
        this.container.classList.add('avatar-3d-ready');

        if (gltf.animations?.length) {
          this.mixer = new THREE.AnimationMixer(this.rig);
          const idleClip = pickClip(gltf.animations, ['idle', 'stand', 'breath', 'rest', 'head']);
          const speakClip = pickClip(gltf.animations, ['talk', 'speak', 'speech', 'mouth']);
          const useSpeak = speakClip && speakClip !== idleClip ? speakClip : idleClip;

          if (idleClip) {
            this.idleAction = this.mixer.clipAction(idleClip);
            this.idleAction.setLoop(THREE.LoopRepeat);
          }
          if (useSpeak) {
            this.speakAction = this.mixer.clipAction(useSpeak);
            this.speakAction.setLoop(THREE.LoopRepeat);
          }
          this.idleAction?.play();
          this._framePortrait();
        }
      },
      undefined,
      (err) => {
        console.error('[ProsecutoAvatar] Failed to load model:', err);
        this.container.classList.add('avatar-3d-error');
      }
    );
  }

  setSpeaking(active) {
    this.speaking = !!active;
    if (!this.mixer) return;

    if (this.speakAction && this.idleAction && this.speakAction !== this.idleAction) {
      const fade = 0.35;
      if (this.speaking) {
        this.idleAction.fadeOut(fade);
        this.speakAction.reset().fadeIn(fade).play();
      } else {
        this.speakAction.fadeOut(fade);
        this.idleAction.reset().fadeIn(fade).play();
      }
      return;
    }

    const action = this.speakAction || this.idleAction;
    if (action) action.timeScale = this.speaking ? 1.35 : 1;
  }

  _tick() {
    if (this.disposed) return;
    const dt = this.clock.getDelta();
    this.mixer?.update(dt);

    if (this.headBone && this.camera) {
      this.headBone.getWorldPosition(this._tmp);
      this.lookTarget.copy(this._tmp);
      this.lookTarget.y -= 0.012;
      this.camera.lookAt(this.lookTarget);
    }

    this.renderer.render(this.scene, this.camera);
    this._raf = requestAnimationFrame(this._tick);
  }

  dispose() {
    this.disposed = true;
    cancelAnimationFrame(this._raf);
    this._ro?.disconnect();
    this.mixer?.stopAllAction();
    this.renderer.dispose();
    this.renderer.domElement.remove();
    this.scene.traverse((obj) => {
      if (obj.geometry) obj.geometry.dispose();
      if (obj.material) {
        const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
        mats.forEach((m) => m.dispose?.());
      }
    });
  }
}

function mount(container, options) {
  if (!container) return null;
  return new AvatarStage(container, options);
}

function AvatarMount({ speaking, modelUrl }) {
  const { useRef, useEffect } = window.React;
  const mountRef = useRef(null);
  const stageRef = useRef(null);

  useEffect(() => {
    const el = mountRef.current;
    if (!el) return undefined;
    stageRef.current = mount(el, { modelUrl });
    return () => {
      stageRef.current?.dispose();
      stageRef.current = null;
    };
  }, [modelUrl]);

  useEffect(() => {
    stageRef.current?.setSpeaking(speaking);
  }, [speaking]);

  return window.React.createElement('div', {
    className: 'avatar-3d-mount',
    ref: mountRef,
    'aria-hidden': true,
  });
}

window.ProsecutoAvatar = { mount, AvatarStage };
window.ProsecutoAvatarMount = AvatarMount;
window.dispatchEvent(new Event('prosecuto-avatar-ready'));
