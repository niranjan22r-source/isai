/*
 * Minimal 10-band stereo biquad EQ for ISAI.
 * Biquad peaking EQ (RBJ cookbook) + preamp.
 * Process interleaved float32 stereo samples in place.
 */
#include <math.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

typedef struct {
    double b0, b1, b2, a1, a2;
    double z1_l, z2_l, z1_r, z2_r;
} Biquad;

typedef struct {
    int enabled;
    double preamp_db;
    double preamp_gain;
    int band_count;
    double freqs[10];
    double gains_db[10];
    double qs[10];
    int sample_rate;
    Biquad bands[10];
} EqState;

static double db_to_lin(double db) {
    return pow(10.0, db / 20.0);
}

static void reset_biquad(Biquad *b) {
    b->z1_l = b->z2_l = b->z1_r = b->z2_r = 0.0;
}

static void set_peaking(Biquad *b, double fs, double freq, double gain_db, double Q) {
    if (fs <= 0.0) fs = 44100.0;
    if (freq < 1.0) freq = 1.0;
    if (freq > fs * 0.499) freq = fs * 0.499;
    if (Q < 0.1) Q = 0.1;
    double A = pow(10.0, gain_db / 40.0);
    double w0 = 2.0 * M_PI * freq / fs;
    double cw = cos(w0);
    double sw = sin(w0);
    double alpha = sw / (2.0 * Q);
    double b0 = 1.0 + alpha * A;
    double b1 = -2.0 * cw;
    double b2 = 1.0 - alpha * A;
    double a0 = 1.0 + alpha / A;
    double a1 = -2.0 * cw;
    double a2 = 1.0 - alpha / A;
    b->b0 = b0 / a0;
    b->b1 = b1 / a0;
    b->b2 = b2 / a0;
    b->a1 = a1 / a0;
    b->a2 = a2 / a0;
}

void eq_init(EqState *s) {
    if (!s) return;
    memset(s, 0, sizeof(*s));
    s->enabled = 1;
    s->preamp_db = 0.0;
    s->preamp_gain = 1.0;
    s->band_count = 10;
    double freqs[10] = {31,62,125,250,500,1000,2000,4000,8000,16000};
    for (int i=0;i<10;i++) { s->freqs[i]=freqs[i]; s->gains_db[i]=0.0; s->qs[i]=1.0; reset_biquad(&s->bands[i]); }
    s->sample_rate = 44100;
}

void eq_set_enabled(EqState *s, int enabled) { if (s) s->enabled = enabled ? 1 : 0; }

void eq_set_preamp(EqState *s, double db) {
    if (!s) return;
    if (db < -24.0) db = -24.0;
    if (db > 24.0) db = 24.0;
    s->preamp_db = db;
    s->preamp_gain = db_to_lin(db);
}

void eq_set_band(EqState *s, int index, double gain_db, double freq, double q) {
    if (!s || index < 0 || index >= s->band_count) return;
    if (gain_db < -24.0) gain_db = -24.0;
    if (gain_db > 24.0) gain_db = 24.0;
    if (q < 0.1) q = 0.1;
    if (q > 16.0) q = 16.0;
    s->gains_db[index] = gain_db;
    s->freqs[index] = freq;
    s->qs[index] = q;
    set_peaking(&s->bands[index], (double)s->sample_rate, freq, gain_db, q);
}

void eq_configure(EqState *s, int sample_rate, int band_count, const double *freqs, const double *gains_db, const double *qs, double preamp_db) {
    if (!s) return;
    if (sample_rate < 8000) sample_rate = 44100;
    s->sample_rate = sample_rate;
    if (band_count < 0) band_count = 0;
    if (band_count > 10) band_count = 10;
    s->band_count = band_count;
    eq_set_preamp(s, preamp_db);
    for (int i=0;i<band_count;i++) {
        double f = freqs ? freqs[i] : s->freqs[i];
        double g = gains_db ? gains_db[i] : 0.0;
        double q = qs ? qs[i] : 1.0;
        eq_set_band(s, i, g, f, q);
    }
    for (int i=band_count;i<10;i++) {
        s->gains_db[i]=0.0; reset_biquad(&s->bands[i]);
    }
}

void eq_reset(EqState *s) {
    if (!s) return;
    eq_set_preamp(s, 0.0);
    for (int i=0;i<s->band_count;i++) {
        eq_set_band(s, i, 0.0, s->freqs[i], s->qs[i]);
        reset_biquad(&s->bands[i]);
    }
}

static inline double clamp_sample(double x) {
    if (x > 1.0) return 1.0;
    if (x < -1.0) return -1.0;
    return x;
}

static inline short clamp_s16(double x) {
    if (x > 1.0) x = 1.0;
    if (x < -1.0) x = -1.0;
    int v = (int)(x * 32767.0);
    if (v > 32767) v = 32767;
    if (v < -32768) v = -32768;
    return (short)v;
}

void eq_process_f32(EqState *s, float *samples, int frames) {
    if (!s || !samples || frames <= 0) return;
    if (!s->enabled) return;
    double pre = s->preamp_gain;
    for (int i=0;i<frames;i++) {
        double l = (double)samples[i*2] * pre;
        double r = (double)samples[i*2+1] * pre;
        for (int b=0;b<s->band_count;b++) {
            Biquad *q = &s->bands[b];
            double y0l = q->b0*l + q->z1_l;
            q->z1_l = q->b1*l - q->a1*y0l + q->z2_l;
            q->z2_l = q->b2*l - q->a2*y0l;
            l = y0l;
            double y0r = q->b0*r + q->z1_r;
            q->z1_r = q->b1*r - q->a1*y0r + q->z2_r;
            q->z2_r = q->b2*r - q->a2*y0r;
            r = y0r;
        }
        samples[i*2] = (float)clamp_sample(l);
        samples[i*2+1] = (float)clamp_sample(r);
    }
}

void eq_process_s16(EqState *s, short *samples, int frames) {
    if (!s || !samples || frames <= 0) return;
    if (!s->enabled) return;
    double pre = s->preamp_gain;
    const double scale = 1.0 / 32768.0;
    for (int i=0;i<frames;i++) {
        double l = (double)samples[i*2] * scale * pre;
        double r = (double)samples[i*2+1] * scale * pre;
        for (int b=0;b<s->band_count;b++) {
            Biquad *q = &s->bands[b];
            double y0l = q->b0*l + q->z1_l;
            q->z1_l = q->b1*l - q->a1*y0l + q->z2_l;
            q->z2_l = q->b2*l - q->a2*y0l;
            l = y0l;
            double y0r = q->b0*r + q->z1_r;
            q->z1_r = q->b1*r - q->a1*y0r + q->z2_r;
            q->z2_r = q->b2*r - q->a2*y0r;
            r = y0r;
        }
        samples[i*2] = clamp_s16(l);
        samples[i*2+1] = clamp_s16(r);
    }
}
