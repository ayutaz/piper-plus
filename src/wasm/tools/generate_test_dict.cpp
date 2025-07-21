/**
 * Test Dictionary Generator
 * 
 * Creates a sample dictionary for testing compression
 */

#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <random>

struct TestEntry {
    std::string surface;
    int left_id;
    int right_id;
    int cost;
    int pos_id;
    std::string reading;
    std::string pronunciation;
    int accent;
};

// Common Japanese words for testing
std::vector<TestEntry> generateCommonWords() {
    return {
        {"私", 1, 2, 100, 10, "ワタシ", "ワタシ", 0},
        {"は", 2, 3, 50, 20, "ハ", "ワ", 0},
        {"です", 3, 4, 80, 30, "デス", "デス", 1},
        {"ます", 3, 4, 80, 30, "マス", "マス", 1},
        {"こんにちは", 1, 4, 120, 40, "コンニチハ", "コンニチワ", 0},
        {"ありがとう", 1, 4, 120, 40, "アリガトウ", "アリガトー", 2},
        {"さようなら", 1, 4, 120, 40, "サヨウナラ", "サヨーナラ", 2},
        {"日本", 1, 2, 100, 10, "ニホン", "ニホン", 1},
        {"東京", 1, 2, 100, 10, "トウキョウ", "トーキョー", 0},
        {"大阪", 1, 2, 100, 10, "オオサカ", "オーサカ", 0},
        {"行く", 2, 3, 90, 50, "イク", "イク", 0},
        {"来る", 2, 3, 90, 50, "クル", "クル", 1},
        {"見る", 2, 3, 90, 50, "ミル", "ミル", 1},
        {"食べる", 2, 3, 90, 50, "タベル", "タベル", 2},
        {"飲む", 2, 3, 90, 50, "ノム", "ノム", 1},
        {"今日", 1, 2, 100, 10, "キョウ", "キョー", 1},
        {"明日", 1, 2, 100, 10, "アシタ", "アシタ", 0},
        {"昨日", 1, 2, 100, 10, "キノウ", "キノー", 2},
        {"天気", 1, 2, 100, 10, "テンキ", "テンキ", 1},
        {"良い", 2, 2, 80, 60, "ヨイ", "ヨイ", 1},
    };
}

// Generate synthetic entries for volume testing
std::vector<TestEntry> generateSyntheticEntries(int count) {
    std::vector<TestEntry> entries;
    std::mt19937 rng(42);  // Fixed seed for reproducibility
    std::uniform_int_distribution<> left_dist(1, 100);
    std::uniform_int_distribution<> right_dist(1, 100);
    std::uniform_int_distribution<> cost_dist(50, 500);
    std::uniform_int_distribution<> pos_dist(1, 60);
    std::uniform_int_distribution<> accent_dist(0, 5);
    
    // Katakana characters for generating readings
    std::vector<std::string> kana = {
        "ア", "イ", "ウ", "エ", "オ",
        "カ", "キ", "ク", "ケ", "コ",
        "サ", "シ", "ス", "セ", "ソ",
        "タ", "チ", "ツ", "テ", "ト",
        "ナ", "ニ", "ヌ", "ネ", "ノ",
        "ハ", "ヒ", "フ", "ヘ", "ホ",
        "マ", "ミ", "ム", "メ", "モ",
        "ヤ", "ユ", "ヨ",
        "ラ", "リ", "ル", "レ", "ロ",
        "ワ", "ン"
    };
    
    std::uniform_int_distribution<> kana_dist(0, kana.size() - 1);
    std::uniform_int_distribution<> length_dist(2, 5);
    
    for (int i = 0; i < count; i++) {
        TestEntry entry;
        
        // Generate surface form
        entry.surface = "単語" + std::to_string(i);
        
        // Random IDs and costs
        entry.left_id = left_dist(rng);
        entry.right_id = right_dist(rng);
        entry.cost = cost_dist(rng);
        entry.pos_id = pos_dist(rng);
        
        // Generate random reading
        int length = length_dist(rng);
        for (int j = 0; j < length; j++) {
            entry.reading += kana[kana_dist(rng)];
        }
        
        // Sometimes pronunciation differs
        if (i % 5 == 0) {
            entry.pronunciation = entry.reading + "ー";
        } else {
            entry.pronunciation = entry.reading;
        }
        
        entry.accent = accent_dist(rng);
        
        entries.push_back(entry);
    }
    
    return entries;
}

int main(int argc, char* argv[]) {
    std::string filename = "test_dict.txt";
    int synthetic_count = 10000;
    
    if (argc > 1) {
        filename = argv[1];
    }
    if (argc > 2) {
        synthetic_count = std::stoi(argv[2]);
    }
    
    std::ofstream file(filename);
    if (!file) {
        std::cerr << "Failed to create: " << filename << std::endl;
        return 1;
    }
    
    // Write header
    file << "# Test Dictionary for MeCab/OpenJTalk\n";
    file << "# Format: surface\\tleft_id\\tright_id\\tcost\\tpos_id\\treading\\tpronunciation\\taccent\n";
    file << "\n";
    
    // Add common words
    auto common = generateCommonWords();
    for (const auto& entry : common) {
        file << entry.surface << "\t"
             << entry.left_id << "\t"
             << entry.right_id << "\t"
             << entry.cost << "\t"
             << entry.pos_id << "\t"
             << entry.reading << "\t"
             << entry.pronunciation << "\t"
             << entry.accent << "\n";
    }
    
    // Add synthetic entries
    auto synthetic = generateSyntheticEntries(synthetic_count);
    for (const auto& entry : synthetic) {
        file << entry.surface << "\t"
             << entry.left_id << "\t"
             << entry.right_id << "\t"
             << entry.cost << "\t"
             << entry.pos_id << "\t"
             << entry.reading << "\t"
             << entry.pronunciation << "\t"
             << entry.accent << "\n";
    }
    
    file.close();
    
    std::cout << "Generated test dictionary: " << filename << std::endl;
    std::cout << "Total entries: " << (common.size() + synthetic.size()) << std::endl;
    std::cout << "  Common words: " << common.size() << std::endl;
    std::cout << "  Synthetic entries: " << synthetic.size() << std::endl;
    
    return 0;
}