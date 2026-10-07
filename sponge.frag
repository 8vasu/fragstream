// fragstream - Run a Shadertoy style fragment shader: serve it live to a browser, or render it without a display to an image, a video or timings
// Copyright (C) 2026 Soumendra Ganguly

// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.

// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <https://www.gnu.org/licenses/>.

// A spinning Menger sponge: a cube with nested square holes, raymarched. The shading takes its ambient
// occlusion and glow from how many steps each ray needed, so no extra lighting passes are needed.
// Written against the Shadertoy interface, so the same file runs headless and in the live viewer.

// --- the sponge ------------------------------------------------------------
const float TAU = 6.28318530718;
const int ITERATIONS = 4;
const vec3 HALF_SIZE = vec3(1.0);

// --- motion ----------------------------------------------------------------
const float SPIN_RATE = 0.25;
const float TUMBLE_RATIO = 0.7;
const float ORBIT_RATE = 0.12;
const float CAMERA_DISTANCE = 4.2;
const float CAMERA_HEIGHT = 0.4;
const float FOCAL = 1.8;

// --- marching and looks ----------------------------------------------------
const int MAX_STEPS = 96;
const float MAX_DIST = 12.0;
const float HIT = 0.0008;
const float OCCLUSION = 1.6;
const float GLOW = 2.5;
const float FOG_DENSITY = 0.05;
const float DISPLAY_GAMMA = 0.4545;

float box(vec3 p, vec3 b) {
    vec3 q = abs(p) - b;

    return length(max(q, 0.0)) + min(max(q.x, max(q.y, q.z)), 0.0);
}

vec3 palette(float x) {
    return 0.5 + 0.5 * cos(TAU * (x + vec3(0.0, 0.1, 0.2)));
}

mat2 turn(float angle) {
    float c = cos(angle);
    float s = sin(angle);

    return mat2(c, -s, s, c);
}

// the sponge's own frame: it spins about one axis and tumbles about another
vec3 spin(vec3 p) {
    float angle = iTime * SPIN_RATE;
    vec2 xz = turn(angle) * p.xz;
    vec3 q = vec3(xz.x, p.y, xz.y);
    vec2 xy = turn(angle * TUMBLE_RATIO) * q.xy;

    return vec3(xy.x, xy.y, q.z);
}

float sponge(vec3 p) {
    p = spin(p);
    float d = box(p, HALF_SIZE);
    float scale = 1.0;

    // each pass cuts a cross of square holes through every cube left, three times smaller than the last
    for (int i = 0; i < ITERATIONS; i++) {
        vec3 cell = mod(p * scale, 2.0) - 1.0;
        scale *= 3.0;
        vec3 r = abs(1.0 - 3.0 * abs(cell));
        float hole = (min(max(r.x, r.y), min(max(r.y, r.z), max(r.z, r.x))) - 1.0) / scale;
        d = max(d, hole);
    }

    return d;
}

// x: distance travelled, y: steps taken as a fraction of the most allowed, z: 1 for a hit
vec3 march(vec3 ro, vec3 rd) {
    float t = 0.0;
    int used = MAX_STEPS;
    float hit = 0.0;

    for (int i = 0; i < MAX_STEPS; i++) {
        float d = sponge(ro + rd * t);
        if (d < HIT) {
            hit = 1.0;
            used = i;
            break;
        }
        t += d;
        if (t > MAX_DIST) {
            used = i;
            break;
        }
    }

    return vec3(t, float(used) / float(MAX_STEPS), hit);
}

vec3 normal(vec3 p) {
    vec2 e = vec2(0.0005, -0.0005);

    return normalize(e.xyy * sponge(p + e.xyy) + e.yyx * sponge(p + e.yyx) +
                     e.yxy * sponge(p + e.yxy) + e.xxx * sponge(p + e.xxx));
}

vec3 backdrop(vec3 rd) {
    return mix(vec3(0.02, 0.03, 0.06), vec3(0.08, 0.05, 0.12), clamp(rd.y * 0.5 + 0.5, 0.0, 1.0));
}

vec3 shade(vec3 ro, vec3 rd, vec3 hit) {
    // a ray that missed still glows if it grazed the sponge, which took it many steps
    if (hit.z < 0.5) {
        return backdrop(rd) + palette(0.6) * pow(hit.y, 2.0) * GLOW;
    }

    vec3 p = ro + rd * hit.x;
    vec3 n = normal(p);
    vec3 light = normalize(vec3(0.6, 0.8, 0.4));
    float occlusion = pow(1.0 - hit.y, 2.0) * OCCLUSION;
    float diffuse = max(dot(n, light), 0.0);
    float rim = pow(1.0 - max(dot(n, -rd), 0.0), 3.0);
    vec3 base = palette(dot(spin(p), vec3(0.25)) + iTime * 0.05);
    vec3 color = base * (0.15 + 0.85 * diffuse) * occlusion + palette(0.55) * rim * 0.6;

    return mix(color, backdrop(rd), 1.0 - exp(-hit.x * FOG_DENSITY));
}

void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    vec2 uv = (2.0 * fragCoord - iResolution.xy) / iResolution.y;

    // the camera orbits the sponge at a fixed height
    float angle = iTime * ORBIT_RATE;
    vec3 ro = vec3(sin(angle), CAMERA_HEIGHT, cos(angle)) * CAMERA_DISTANCE;
    vec3 forward = normalize(-ro);
    vec3 right = normalize(cross(forward, vec3(0.0, 1.0, 0.0)));
    vec3 up = cross(right, forward);
    vec3 rd = normalize(uv.x * right + uv.y * up + FOCAL * forward);

    // tone map, then encode for display
    vec3 color = shade(ro, rd, march(ro, rd));
    color = color / (1.0 + color);
    fragColor = vec4(pow(color, vec3(DISPLAY_GAMMA)), 1.0);
}
