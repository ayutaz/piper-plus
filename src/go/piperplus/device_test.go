package piperplus

import "testing"

func TestParseDevice(t *testing.T) {
	tests := []struct {
		input    string
		provider string
		deviceID int
		wantErr  bool
	}{
		{input: "cpu", provider: "cpu", deviceID: 0},
		{input: "CPU", provider: "cpu", deviceID: 0},
		{input: "cuda", provider: "cuda", deviceID: 0},
		{input: "cuda:0", provider: "cuda", deviceID: 0},
		{input: "cuda:1", provider: "cuda", deviceID: 1},
		{input: "CUDA:2", provider: "cuda", deviceID: 2},
		{input: "coreml", provider: "coreml", deviceID: 0},
		{input: "directml", provider: "directml", deviceID: 0},
		{input: "directml:1", provider: "directml", deviceID: 1},
		{input: "tensorrt", provider: "tensorrt", deviceID: 0},
		{input: "tensorrt:0", provider: "tensorrt", deviceID: 0},
		{input: "auto", provider: "auto", deviceID: 0},
		{input: "", provider: "cpu", deviceID: 0},
		{input: "invalid", wantErr: true},
		{input: "cuda:abc", wantErr: true},
		{input: "cuda:-1", wantErr: true},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			got, err := ParseDevice(tt.input)
			if tt.wantErr {
				if err == nil {
					t.Fatalf("ParseDevice(%q) returned nil error, want error", tt.input)
				}
				return
			}
			if err != nil {
				t.Fatalf("ParseDevice(%q) returned unexpected error: %v", tt.input, err)
			}
			if got.Provider != tt.provider {
				t.Errorf("ParseDevice(%q).Provider = %q, want %q", tt.input, got.Provider, tt.provider)
			}
			if got.DeviceID != tt.deviceID {
				t.Errorf("ParseDevice(%q).DeviceID = %d, want %d", tt.input, got.DeviceID, tt.deviceID)
			}
		})
	}
}

func TestDeviceType_String(t *testing.T) {
	tests := []struct {
		device DeviceType
		want   string
	}{
		{device: DeviceType{"cpu", 0}, want: "cpu"},
		{device: DeviceType{"cuda", 0}, want: "cuda:0"},
		{device: DeviceType{"cuda", 1}, want: "cuda:1"},
		{device: DeviceType{"coreml", 0}, want: "coreml"},
		{device: DeviceType{"directml", 0}, want: "directml:0"},
	}

	for _, tt := range tests {
		t.Run(tt.want, func(t *testing.T) {
			if got := tt.device.String(); got != tt.want {
				t.Errorf("DeviceType%+v.String() = %q, want %q", tt.device, got, tt.want)
			}
		})
	}
}
